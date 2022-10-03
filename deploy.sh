#!/bin/bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml build --no-cache
docker-compose down
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
