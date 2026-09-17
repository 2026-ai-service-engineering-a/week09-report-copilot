-- 처음 기동에 한 번만 돈다 (docker-entrypoint-initdb.d).
--
-- 여기서 만드는 것 둘.
--   ① reader: SELECT만 할 수 있는 계정. api가 이걸로 붙는다.
--      모델이 질의를 짜는 제품에서는 게이트가 둘이어야 한다. 애플리케이션의
--      gate_query가 첫 층이고, 이 권한이 둘째 층이다 (교안 9장 1절)
--   ② litellm: 게이트웨이의 장부가 쓸 데이터베이스

CREATE ROLE reader LOGIN PASSWORD 'reader';

GRANT CONNECT ON DATABASE boxoffice TO reader;
GRANT USAGE ON SCHEMA public TO reader;
-- 지금 있는 것과 앞으로 생길 것 모두에 SELECT만 준다
GRANT SELECT ON ALL TABLES IN SCHEMA public TO reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO reader;

CREATE DATABASE litellm OWNER report;
