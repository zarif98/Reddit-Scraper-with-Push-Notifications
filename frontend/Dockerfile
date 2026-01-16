# Frontend Dockerfile for Next.js
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Build argument for API URL (will be baked into the build)
ARG NEXT_PUBLIC_API_URL=http://localhost:5001
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# Build the application
RUN npm run build

# Production stage
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
# API URL can be overridden at runtime for private Docker networks
# If not set, frontend uses dynamic hostname detection
ENV NEXT_PUBLIC_API_URL=""

# Copy built assets from builder
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

# Copy public folder if it exists (use separate RUN to handle missing dir)
RUN mkdir -p ./public

EXPOSE 3000

CMD ["node", "server.js"]
