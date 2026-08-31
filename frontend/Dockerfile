# Frontend Dockerfile (Vite dev server for demo)
FROM node:20-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 5173

# Vite dev server — env vars (VITE_API_BASE_URL) are injected by docker-compose
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
