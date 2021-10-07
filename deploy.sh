#!/bin/bash
docker-compose down
docker volume rm -f normal-oj_vue-dist
docker-compose -f docker-compose.yml -f docker-compose.prod.yml build --no-cache
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
