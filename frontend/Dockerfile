FROM node:20-alpine AS builder
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM node:20-alpine AS runtime
WORKDIR /app
COPY --from=builder /src/dist ./dist
COPY frontend/serve.cjs ./serve.cjs
RUN addgroup -S app && adduser -S -G app app && chown -R app:app /app
USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=5 \
  CMD node -e "require('http').get('http://127.0.0.1:8080/',{timeout:5000},r=>{if(!r||r.statusCode!==200)process.exit(1)}).on('error',()=>process.exit(1))"
ENV PORT=8080
CMD ["node", "serve.cjs"]