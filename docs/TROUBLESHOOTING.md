# Troubleshooting Guide

## Common Issues

### 🌐 Network and Browser Issues

**ERR_INSUFFICIENT_RESOURCES**
- **Problem**: Browser runs out of network connections when loading Task Data Dashboard
- **Solution**: Fixed in Issue #171 with request debouncing, connection pooling, and proper error handling
- **Details**: See [ERR_INSUFFICIENT_RESOURCES Error Resolution](./troubleshooting/err-insufficient-resources.md)

### 🔐 Authentication Problems

**401 Unauthorized on API calls**
```bash
# Check JWT token validity
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/users/me

# Get new token
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"user@example.com","password":"password"}'
```

**Cannot access Native Annotation System**
- Ensure you're logged into BenGER first
- Check if Native Annotation System service is running: `docker ps | grep native-annotation`
- Verify environment variables: `native_annotation_URL`, `native_annotation_TOKEN`
- Try direct access: http://localhost:8080

**Session expires quickly**
- Check JWT expiration in backend config
- Verify token refresh is working in frontend
- Clear browser storage and login again

### 🗄️ Database Issues

**Connection refused**
```bash
# Check PostgreSQL is running
docker ps | grep postgres

# Test connection
docker exec -it benger-postgres psql -U postgres -d benger -c "SELECT version();"

# Check logs
docker logs benger-postgres
```

**Migration failures**
```bash
# Reset migrations (DEVELOPMENT ONLY)
cd services/api
alembic downgrade base
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "Description"
```

**Missing tables/data**
```bash
# Check table existence
docker exec -it benger-postgres psql -U postgres -d benger -c "\dt"

# Restore from backup (if available)
docker exec -i benger-postgres psql -U postgres -d benger < backup.sql
```

### 🐳 Docker & Container Issues

**Port conflicts**
```bash
# Check port usage
lsof -i :3000  # Frontend
lsof -i :8000  # API  
lsof -i :8080  # Native Annotation System

# Change ports in docker-compose.yml if needed
```

**Out of disk space**
```bash
# Clean Docker system
docker system prune -a --volumes

# Remove unused images
docker image prune -a

# Check disk usage
df -h
docker system df
```

**Container won't start**
```bash
# Check logs
docker logs <container-name>

# Check configuration
docker inspect <container-name>

# Restart services
docker-compose down && docker-compose up -d
```

### 📱 Frontend Issues

**Page won't load / Blank screen**
- Check browser console for JavaScript errors
- Verify API connectivity: Open Network tab in DevTools
- Clear browser cache and cookies
- Try incognito/private mode

**API endpoints returning 404**
```bash
# Check API is running
curl http://localhost:8000/api/healthz

# Verify routes in backend
curl http://localhost:8000/docs

# Check frontend API configuration
cat services/frontend/.env.local
```

**Build failures**
```bash
# Clear Next.js cache
cd services/frontend
rm -rf .next
npm run build

# Check Node.js version
node --version  # Should be 20+

# Reinstall dependencies
rm -rf node_modules package-lock.json
npm install
```

### 🔄 File Upload Issues

**Upload fails**
- Check file size limits (default: 100MB)
- Verify supported formats: PDF, DOCX, TXT, JSON
- Ensure stable internet connection
- Try smaller files first

**Files not appearing in Native Annotation System**
- Wait for sync to complete (can take 1-2 minutes)
- Check task configuration and annotation schema
- Verify Native Annotation System project was created
- Check API logs for sync errors

```bash
# Check sync status
curl http://localhost:8000/api/tasks/{task_id}/sync-status

# Manual sync trigger
curl -X POST http://localhost:8000/api/tasks/{task_id}/sync
```

### ☸️ Kubernetes Issues (Production)

**Pods not starting**
```bash
# Check pod status
kubectl get pods -n benger

# Check events
kubectl describe pod <pod-name> -n benger

# Check logs
kubectl logs <pod-name> -n benger

# Check resource usage
kubectl top nodes
kubectl top pods -n benger
```

**Services unreachable**
```bash
# Check services
kubectl get svc -n benger

# Check ingress
kubectl get ing -n benger

# Test internal connectivity
kubectl exec -it <pod-name> -- curl http://service-name:port
```

**Certificate issues**
```bash
# Check certificate status
kubectl get certificates -n benger

# Force renewal
kubectl delete certificate <cert-name> -n benger

# Check cert-manager logs
kubectl logs -n cert-manager deployment/cert-manager
```

## Performance Issues

### 🐌 Slow Response Times

**Database queries**
```sql
-- Check slow queries
SELECT query, mean_exec_time, calls 
FROM pg_stat_statements 
ORDER BY mean_exec_time DESC LIMIT 10;

-- Check index usage
SELECT schemaname, tablename, attname, n_distinct, correlation 
FROM pg_stats WHERE tablename = 'your_table';
```

**High memory usage**
```bash
# Check container memory
docker stats

# Check system memory
free -h
htop

# Restart services to clear memory
docker-compose restart
```

**API bottlenecks**
- Enable API logging and profiling
- Check database connection pooling
- Monitor Redis performance
- Scale horizontally if needed

### 📊 Resource Monitoring

**System health checks**
```bash
# API health
curl http://localhost:8000/api/healthz

# Database health
docker exec benger-postgres pg_isready

# Redis health
docker exec benger-redis redis-cli ping

# Disk space
df -h
```

## Development Issues

### 🛠️ Local Development

**Hot reload not working**
```bash
# Frontend
cd services/frontend
rm -rf .next node_modules
npm install
npm run dev

# API
cd services/api
pip install -e .
uvicorn main:app --reload
```

**Environment variable issues**
```bash
# Check .env file exists
ls -la .env*

# Verify variables loaded
docker-compose config

# Print environment in container
docker exec <container> env | grep VARIABLE_NAME
```

**Code changes not reflected**
- Ensure volumes are mounted correctly in docker-compose.yml
- Check file permissions (especially on Windows/WSL)
- Restart containers if needed
- Clear application caches

### 🧪 Testing Issues

**Tests failing**
```bash
# Run with verbose output
cd services/api
pytest -v -s

cd services/frontend  
npm test -- --verbose

# Check test database
docker exec -it benger-postgres-test psql -U postgres -l
```

**E2E test failures**
- Ensure all services are running
- Check test environment configuration
- Verify test data setup
- Run tests in isolation

## Recovery Procedures

### 🔄 Service Recovery

**Complete system restart**
```bash
# Stop all services
docker-compose down

# Remove volumes (CAUTION: Data loss)
docker-compose down -v

# Clean restart
docker-compose up -d --force-recreate
```

**Database recovery**
```bash
# From backup
docker exec -i benger-postgres psql -U postgres -d benger < backup.sql

# Reset to clean state
docker-compose down -v
docker-compose up -d postgres
# Wait for initialization, then start other services
```

### 🆘 Emergency Procedures

**Production incident response**
1. **Assess impact**: Check service status and user reports
2. **Stabilize**: Scale down problematic services
3. **Investigate**: Check logs and metrics
4. **Fix**: Apply hotfix or rollback
5. **Monitor**: Verify resolution
6. **Post-mortem**: Document and improve

**Data corruption**
1. **Stop writes**: Scale down to read-only mode
2. **Assess damage**: Check data integrity
3. **Restore**: From most recent clean backup
4. **Validate**: Verify data consistency
5. **Resume**: Gradually restore write access

## Getting Help

### 📞 Support Channels

1. **Documentation**: Check relevant guide sections
2. **Logs**: Always include relevant log output
3. **GitHub Issues**: Create detailed issue with reproduction steps
4. **Team Contact**: For urgent production issues

### 🐛 Bug Reports

**Include this information**:
- **Environment**: Development/Production, OS, browser
- **Steps to reproduce**: Exact sequence that causes issue
- **Expected vs actual behavior**: What should vs does happen
- **Logs**: Relevant error messages and stack traces
- **Screenshots**: For UI issues
- **Configuration**: Relevant environment variables or settings

**Template**:
```markdown
## Environment
- OS: macOS 14.0
- Browser: Chrome 120
- Environment: Local development

## Steps to Reproduce
1. Login as admin user
2. Navigate to /admin/users
3. Click "Change Role" button
4. Error appears

## Expected Behavior
Role change modal should open

## Actual Behavior
500 error: "TypeError: Cannot read property..."

## Logs
[Paste relevant logs here]
``` 