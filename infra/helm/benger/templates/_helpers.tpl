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
