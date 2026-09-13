FROM node:20-alpine

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

# NEXT_PUBLIC_* vars are inlined into the client bundle at build time, so this
# has to be a build arg, not a plain runtime environment variable.
ARG NEXT_PUBLIC_API_BASE=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE

RUN npm run build

CMD ["npm", "start"]
