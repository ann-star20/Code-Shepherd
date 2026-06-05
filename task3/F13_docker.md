---
source_of_truth:
  - task3.md
  - docs/PRD-indfa.md #(§5.2 컨테이너 구성 원칙, §5.3 완전 무상태 컨테이너 정책)
---
## F13: Nginx + Dockerfile (Multi-stage)

### SDD

**파일**: `frontend/Dockerfile`
```dockerfile
# Stage 1: Build
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build        # dist/ 생성

# Stage 2: Serve
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 3000
```

**파일**: `frontend/nginx.conf`
```nginx
server {
    listen 3000;
    root /usr/share/nginx/html;
    index index.html;

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 프록시 (운영 환경)
    location /api/ {
        proxy_pass http://backend:8000/api/;
    }

    # gzip
    gzip on;
    gzip_types text/plain application/javascript text/css application/json;

    # 정적 자산 캐시
    location ~* \.(js|css|png|jpg|svg|ico)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

### TDD (AAA)

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_F13_build | `npm run build` | 빌드 실행 | `dist/index.html` 생성, 에러 없음 |
| T_F13_docker_build | `docker build -t frontend .` | Docker 빌드 | 이미지 생성 성공 |
| T_F13_nginx_spa | `curl http://localhost:3000/some/path` | Nginx 응답 | `index.html` 반환 (SPA fallback) |

### COMMIT
```
chore(infra): add frontend multi-stage Dockerfile nginx SPA config with gzip and cache headers
```
