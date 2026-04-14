# BenGER Helm Chart

This Helm chart deploys the BenGER application to Kubernetes.

## Components

- **API**: FastAPI backend service
- **Frontend**: Next.js frontend application
- **Workers**: Celery workers for async tasks
- **PostgreSQL**: Database (optional, can use external)
- **Redis**: Cache and message broker (optional, can use external)

## Installation

```bash
helm install benger ./infra/helm/benger
```

## Configuration

Key configuration values are in `values.yaml`:

- `global.domain`: The base domain for the application (e.g., `what-a-benger.net`)
- `global.environment`: Environment setting (must be `production` for proper authentication)

## Template Evaluation for Dynamic URLs

This chart uses Helm's `tpl` function to evaluate nested template expressions in environment variables. This is specifically implemented for URL-based environment variables that reference the global domain:

- `FRONTEND_URL`: Evaluates to `https://{{ .Values.global.domain }}`
- `NEXT_PUBLIC_API_URL`: Evaluates to `https://api.{{ .Values.global.domain }}`

### Implementation Pattern

For environment variables that contain template syntax, the deployment templates use conditional logic:

```yaml
{{- if eq .name "FRONTEND_URL" }}
value: {{ tpl .value $ | quote }}
{{- else }}
value: {{ .value | quote }}
{{- end }}
```

This ensures that template expressions within the values are properly evaluated before being set as environment variables in the pods.

### Testing

To verify URL rendering is working correctly:

```bash
# Run the shell test script
./test_helm_url_rendering.sh

# Or run the Python test
python3 ../../tests/test_helm_template_rendering.py
```

## Secrets

The chart expects the following secrets to be created:

- `benger-postgres-credentials`: PostgreSQL connection details
- `benger-redis-credentials`: Redis connection details
- `benger-api-secrets`: API secret keys
- `benger-email-config`: Email service configuration (optional)

## Ingress

The chart includes ingress configuration for exposing services. Configure TLS and domain settings in `values.yaml`.

## Troubleshooting

### Email Verification Links

If email verification links contain template syntax like `{{ .Values.global.domain }}`, ensure that:
1. The deployment templates are using the `tpl` function for URL environment variables
2. The Helm chart is properly installed/upgraded with the latest templates
3. Run the test scripts to verify URL rendering

For more details, see issue #458.