# syntax=docker/dockerfile:1
# 빌드는 node로, 서빙은 nginx로. 나가는 것은 정적 파일뿐이다.
# 8주차 ui와 같은 구성이고, 이번에는 디자인 시스템 없이 순수 React만 쓴다.
# 이 화면의 주인공은 생김새가 아니라 src/agui.ts의 프로토콜이기 때문이다.
FROM node:22-alpine AS build
WORKDIR /ui
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /ui/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
