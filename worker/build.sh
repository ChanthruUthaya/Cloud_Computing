docker build -t worker .
docker tag worker chanthruuthaya/workersec:latest
docker push chanthruuthaya/workersec:latest