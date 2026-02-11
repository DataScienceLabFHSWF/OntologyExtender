#!/bin/bash
# Run the Law Graph service for GraphRAG queries

set -e

echo "Starting Law Graph service..."

# Check if Docker is available
if command -v docker &> /dev/null; then
    echo "Using Docker to run Neo4j Law Graph..."

    # Run Neo4j with law graph data
    docker run \
        --name law-graph \
        --detach \
        --publish 7474:7474 \
        --publish 7687:7687 \
        --env NEO4J_AUTH=neo4j/password \
        --env NEO4J_PLUGINS='["graph-data-science"]' \
        --volume "$(pwd)/data/law_graph:/data" \
        neo4j:5.15

    echo "Law Graph service started on http://localhost:7474"
    echo "Username: neo4j"
    echo "Password: password"

elif command -v neo4j &> /dev/null; then
    echo "Using local Neo4j installation..."

    # Set environment variables for Neo4j
    export NEO4J_HOME="${NEO4J_HOME:-/usr/local/neo4j}"
    export NEO4J_CONF="${NEO4J_HOME}/conf"

    # Start Neo4j service
    neo4j start

    echo "Law Graph service started locally"

else
    echo "ERROR: Neither Docker nor local Neo4j installation found."
    echo "Please install Neo4j or Docker to run the Law Graph service."
    exit 1
fi

# Wait for service to be ready
echo "Waiting for Law Graph service to be ready..."
sleep 10

# Test connection
if curl -s -u neo4j:password http://localhost:7474/db/data/ > /dev/null; then
    echo "✓ Law Graph service is ready and accessible"
else
    echo "✗ Law Graph service failed to start properly"
    exit 1
fi

echo "Law Graph service is running in the background."
echo "To stop: docker stop law-graph (if using Docker) or neo4j stop (if local)"