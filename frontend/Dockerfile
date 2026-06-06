FROM node:20-slim
WORKDIR /app

# Install frontend dependencies first so Docker can reuse the layer.
COPY package.json ./
RUN npm install

# Copy the React/Vite app after dependencies are ready.
COPY . .

# Vite serves the technician workspace on port 5173.
EXPOSE 5173

# Run the dev server so the hackathon demo reloads quickly.
CMD ["npm", "run", "dev"]
