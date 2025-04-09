#!/bin/bash
set -e

# Build and push Docker image to DockerHub
echo "Building Docker images..."
targets=(
    scrape_shares insert_shares
    scrape_bonds insert_bonds
    scrape_indices insert_indices
    scrape_dividends insert_dividends
    scrape_capitalizations insert_capitalizations
)

#for target in "${targets[@]}"; do
#    docker build -f scripts/Dockerfile scripts/ --no-cache --target $target -t issacamara/$target:latest
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
## Get the service URL
#SERVICE_URL=$(terraform output -raw service_url)
#echo "Application deployed successfully at: $SERVICE_URL"

for target in "${targets[@]}"; do
#    rm -f terraform/$target.zip
done