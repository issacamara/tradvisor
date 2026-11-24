#!/bin/bash
set -e

# Build and push Docker image to DockerHub
echo "Building Docker images..."
targets=(
    scrape_shares insert_shares
    scrape_dividends insert_dividends
)

#for target in "${targets[@]}"; do
#    docker build -f functions/ingestion/Dockerfile functions/ingestion/ --no-cache --target $target -t issacamara/$target:latest
#done

#docker build -t issacamara/tradvisor:latest . --platform linux/amd64

echo "Logging in to DockerHub..."
docker login
#for target in "${targets[@]}"; do
#    docker push issacamara/$target:latest
#done

# You should have logged in with 'docker login' before running this script
# or you can add the login command here (not recommended for security reasons)

#echo "Pushing image to DockerHub..."
#docker push issacamara/tradvisor:latest


## Apply Terraform configuration
#echo "Initializing Terraform..."
#terraform init
#
#echo "Applying Terraform configuration..."
#terraform apply -auto-approve
#
## Review Terraform outputs after apply:
#terraform output

for target in "${targets[@]}"; do
#    rm -f terraform/$target.zip
done
