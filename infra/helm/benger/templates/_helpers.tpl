{{/*
Storage environment for the api + workers containers (issue #158).

Injected ONLY when .Values.minio.enabled is true. When MinIO is disabled (the
default) none of these vars are set, so the storage singleton falls back to
STORAGE_TYPE=local and behavior is identical to today's — that is what lets the
chart ride to prod inert until MinIO is deliberately turned on.

The singleton (services/shared/storage/object_storage.py) reads the canonical
names below: STORAGE_TYPE / S3_ENDPOINT_URL / S3_ACCESS_KEY / S3_SECRET_KEY /
S3_BUCKET_NAME / S3_USE_SSL / STORAGE_BASE_URL. STORAGE_BASE_URL is the public
host used to *sign* browser-bound presigned URLs (SigV4 binds the host); the
internal S3_ENDPOINT_URL is used for the upload itself.

S3_ACCESS_KEY / S3_SECRET_KEY come from a pre-created Secret (default
benger-minio-credentials); the same keys are reused as the MinIO root
credentials, so the app authenticates as the MinIO root user.
*/}}
{{- define "benger.storageEnv" -}}
- name: STORAGE_TYPE
  value: {{ .Values.minio.storageType | default "minio" | quote }}
- name: S3_ENDPOINT_URL
  value: {{ .Values.minio.internalEndpoint | default (printf "http://%s-minio:9000" .Release.Name) | quote }}
- name: S3_USE_SSL
  value: "false"
- name: S3_BUCKET_NAME
  value: {{ .Values.minio.bucket | default "benger-exports" | quote }}
- name: S3_REGION
  value: {{ .Values.minio.region | default "us-east-1" | quote }}
- name: STORAGE_BASE_URL
  value: {{ printf "https://%s" (required "minio.publicHost is required when minio.enabled=true" .Values.minio.publicHost) | quote }}
- name: S3_ACCESS_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.minio.credentialsSecret | default "benger-minio-credentials" }}
      key: {{ .Values.minio.accessKeySecretKey | default "access-key" }}
- name: S3_SECRET_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.minio.credentialsSecret | default "benger-minio-credentials" }}
      key: {{ .Values.minio.secretKeySecretKey | default "secret-key" }}
{{- end -}}

{{/*
Pod imagePullSecrets rendered from global.imagePullSecrets. Accepts both
plain-string entries (["ghcr-secret"] — the canonical form; the bitnami
subcharts' common helpers stringify map entries into bogus secret names
like "map[name:ghcr-secret]", so global MUST stay string-form) and the
k8s-native map form ([{name: ghcr-secret}]) for older values overrides.
*/}}
{{- define "benger.imagePullSecrets" -}}
{{- with .Values.global.imagePullSecrets }}
imagePullSecrets:
{{- range . }}
{{- if kindIs "string" . }}
  - name: {{ . }}
{{- else }}
  - name: {{ .name }}
{{- end }}
{{- end }}
{{- end }}
{{- end -}}

{{/*
Traefik headers middleware spec shared by security-headers and
security-headers-frameable. Call with (dict "root" $ "frameDeny" true|false).
The two middlewares differ only in frameDeny.
*/}}
{{- define "benger.securityHeadersSpec" -}}
{{- $root := .root -}}
headers:
  stsSeconds: {{ $root.Values.middleware.securityHeaders.stsSeconds | default 300 }}
  stsIncludeSubdomains: {{ $root.Values.middleware.securityHeaders.stsIncludeSubdomains | default false }}
  stsPreload: {{ $root.Values.middleware.securityHeaders.stsPreload | default false }}
  contentTypeNosniff: true
  {{- if .frameDeny }}
  frameDeny: true
  {{- end }}
  browserXssFilter: true
  referrerPolicy: "strict-origin-when-cross-origin"
  customResponseHeaders:
    Server: ""
    X-Powered-By: ""
    {{- if $root.Values.middleware.noindex }}
    # Keep search engines out of non-production hosts (demo/staging). The
    # header applies to every router that carries a security-headers
    # middleware: api, frontend, the vertretbar apex and the LTI
    # registration page.
    X-Robots-Tag: "noindex, nofollow"
    {{- end }}
{{- end -}}

{{/*
Router priority of the LTI Dynamic Registration Ingresses. It must beat the
frontend catch-all on the same host (values: 100 prod, 150 staging and demo)
and the vertretbar-lti Ingress (110). Only exact hosts are routed, never a
wildcard, so the value cannot capture another namespace's host.
*/}}
{{- define "benger.ltiRegisterPriority" -}}
190
{{- end -}}

{{/*
Extension overlay environment (platform core 2.37). Call with
(dict "root" $ "role" "api"|"workers"). Renders, for every enabled entry of
.Values.overlays in ascending `order` (ties broken by name), the entry's
env list for the role, then BENGER_EXTENSIONS (the enabled packages in that
order) and BENGER_REQUIRE_EXTENSIONS (the `required` ones among them).
Renders nothing when no overlay is enabled, so the registry falls back to
its default (benger_extended) and the legacy BENGER_REQUIRE_EXTENDED.

The deployment templates include this AFTER {api,workers}.extraEnv: the
kubelet keeps the last value of a duplicated env name, so an overlay's
value wins over extraEnv.

Sorting: Helm has no sort-by-key for lists of maps, so each enabled entry is
keyed as "<zero-padded order>|<name>" and sortAlpha orders the keys; `order`
must therefore be a non-negative integer below 10^8.
*/}}
{{- define "benger.overlayEnv" -}}
{{- $root := .root -}}
{{- $role := .role -}}
{{- $overlays := $root.Values.overlays | default dict -}}
{{- $keys := list -}}
{{- range $name, $cfg := $overlays -}}
{{- if and $cfg $cfg.enabled -}}
{{- $order := int ($cfg.order | default 100) -}}
{{- $keys = append $keys (printf "%08d|%s" $order $name) -}}
{{- end -}}
{{- end -}}
{{- $packages := list -}}
{{- $required := list -}}
{{- $lines := list -}}
{{- range $key := sortAlpha $keys -}}
{{- $name := index (splitList "|" $key) 1 -}}
{{- $cfg := index $overlays $name -}}
{{- $package := $cfg.package | default (printf "benger_%s" $name) -}}
{{- $packages = append $packages $package -}}
{{- if $cfg.required -}}
{{- $required = append $required $package -}}
{{- end -}}
{{- $roleCfg := index $cfg $role | default dict -}}
{{- with $roleCfg.env -}}
{{- $lines = append $lines (toYaml .) -}}
{{- end -}}
{{- end -}}
{{- if $packages -}}
{{- $lines = append $lines (printf "- name: BENGER_EXTENSIONS\n  value: %s" (join "," $packages | quote)) -}}
{{- $lines = append $lines (printf "- name: BENGER_REQUIRE_EXTENSIONS\n  value: %s" (join "," $required | quote)) -}}
{{- end -}}
{{- join "\n" $lines -}}
{{- end -}}

{{/*
Pod and container securityContext for every workload this chart templates
(audit 2026-10-31, S5 cluster part).

The baseline lives in .Values.securityContext (enabled, pod, container). A
component may override it with its own `securityContext` map of the same
shape; a component without one inherits the baseline unchanged. Call with
  (dict "root" $ "component" .Values.<component>.securityContext)
and optionally "defaults" (a map of the same shape) for template-level
defaults that sit between the baseline and the component override.

Merging is key by key on the `pod` and `container` maps, done by hand on
purpose: sprig's merge/mergeOverwrite skip "empty" source values, so an
override such as `runAsUser: 0` or `runAsNonRoot: false` would silently lose
against the baseline. A key replaces the baseline key wholesale (for example
`capabilities` or `seccompProfile`).

Emergency switch: `--set securityContext.enabled=false` drops both blocks
from every workload; `<component>.securityContext.enabled=false` drops them
from one workload only.
*/}}
{{- define "benger.securityContexts" -}}
{{- $base := .root.Values.securityContext | default dict -}}
{{- $defaults := .defaults | default dict -}}
{{- $override := .component | default dict -}}
{{- $enabled := true -}}
{{- if hasKey $base "enabled" }}{{- $enabled = $base.enabled -}}{{- end -}}
{{- if and $enabled (hasKey $defaults "enabled") }}{{- $enabled = $defaults.enabled -}}{{- end -}}
{{- if and $enabled (hasKey $override "enabled") }}{{- $enabled = $override.enabled -}}{{- end -}}
{{- $pod := dict -}}
{{- $container := dict -}}
{{- if $enabled -}}
{{- range $layer := list $base $defaults $override -}}
{{- range $k, $v := ($layer.pod | default dict) }}{{- $_ := set $pod $k $v -}}{{- end -}}
{{- range $k, $v := ($layer.container | default dict) }}{{- $_ := set $container $k $v -}}{{- end -}}
{{- end -}}
{{- end -}}
{{- toJson (dict "pod" $pod "container" $container) -}}
{{- end -}}

{{/*
Renders `securityContext:` for a pod spec (or nothing when disabled).
Same arguments as benger.securityContexts.
*/}}
{{- define "benger.podSecurityContext" -}}
{{- $sc := include "benger.securityContexts" . | fromJson -}}
{{- with $sc.pod }}
securityContext:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end -}}

{{/*
Renders `securityContext:` for a container (or nothing when disabled).
Same arguments as benger.securityContexts.
*/}}
{{- define "benger.containerSecurityContext" -}}
{{- $sc := include "benger.securityContexts" . | fromJson -}}
{{- with $sc.container }}
securityContext:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end -}}

{{/*
Hugging Face cache environment for the Celery worker containers (audit E10).
The worker image bakes the embedding models into HF_HOME at build time, and
HF_HUB_OFFLINE=1 stops the libraries from contacting the Hub at runtime, so a
pod start or a fork never downloads a model (no runtime egress to the Hub, no
cold start that depends on huggingface.co being up, no writes into the image).

Call with (dict "root" $ "cfg" <modelCache map> "existing" <list of env lists>).
`cfg` is workers.modelCache, optionally overridden per pool by
workerPools.<pool>.modelCache. Any name that already appears in one of the
`existing` env lists (workers.env, workers.extraEnv, a pool's extraEnv, the
overlay env) is skipped, so this helper can never render a duplicate env name
(the 2026-10-15 "The order in patch list" trap). An explicit entry elsewhere
therefore wins over this default.
*/}}
{{- define "benger.workerModelCacheEnv" -}}
{{- $cfg := .cfg | default dict -}}
{{- if $cfg.enabled -}}
{{- $taken := dict -}}
{{- range $list := .existing -}}
{{- range $e := ($list | default list) -}}
{{- if and (kindIs "map" $e) $e.name }}{{- $_ := set $taken $e.name true -}}{{- end -}}
{{- end -}}
{{- end -}}
{{- $lines := list -}}
{{- if and $cfg.hfHome (not (hasKey $taken "HF_HOME")) -}}
{{- $lines = append $lines (printf "- name: HF_HOME\n  value: %s" ($cfg.hfHome | quote)) -}}
{{- end -}}
{{- if not (hasKey $taken "HF_HUB_OFFLINE") -}}
{{- $lines = append $lines (printf "- name: HF_HUB_OFFLINE\n  value: %s" (ternary "1" "0" (eq (toString $cfg.offline) "true") | quote)) -}}
{{- end -}}
{{- join "\n" $lines -}}
{{- end -}}
{{- end -}}

{{/*
Labels shared by the NetworkPolicies in networkpolicy.yaml.
*/}}
{{- define "benger.networkPolicyLabels" -}}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: network-policy
app.kubernetes.io/part-of: benger
app.kubernetes.io/managed-by: helm
{{- end -}}
