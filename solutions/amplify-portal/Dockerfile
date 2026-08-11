# Container deployment alternative for teams using EKS/Fargate/ECS
# Build: npm run docker:build
# Run:   npm run docker:run (serves on port 8080)
#
# Note: This serves the static frontend only.
# Backend (AppSync/Lambda) still runs in AWS — configure amplify_outputs.json.
FROM node:24-alpine AS builder
WORKDIR /app
COPY package*.json ./
# node:20-alpine used to be the base and no longer installs: several transitive
# packages require node ^22.13 || >=24, so `npm ci` failed on EBADENGINE before it
# reached the build.
RUN npm ci
COPY . .
# src/main.tsx imports ../amplify_outputs.json, which `ampx sandbox` generates and
# .gitignore excludes, so it is absent on a clean clone. A placeholder is enough for
# the module to resolve; the real values belong to a deployed backend. This mirrors
# the same step in .github/workflows/ci.yml.
RUN [ -f amplify_outputs.json ] || echo '{"version":"1.4"}' > amplify_outputs.json
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
# COPY accepts no shell syntax. This line used to end with `2>/dev/null || true`,
# which Docker read as three additional source paths, so the build failed here every
# time it got this far.
COPY --from=builder /app/amplify_outputs.json /usr/share/nginx/html/
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
