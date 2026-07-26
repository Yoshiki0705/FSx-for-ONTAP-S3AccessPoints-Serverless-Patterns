# Container deployment alternative for teams using EKS/Fargate/ECS
# Build: npm run docker:build
# Run:   npm run docker:run (serves on port 8080)
#
# Note: This serves the static frontend only.
# Backend (AppSync/Lambda) still runs in AWS — configure amplify_outputs.json.

FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY --from=builder /app/amplify_outputs.json /usr/share/nginx/html/ 2>/dev/null || true
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
