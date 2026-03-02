"""Test fixtures for API tests."""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from ontology_hitl.api.server import app


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def mock_sparql_query():
    """Mock SPARQL query helper."""
    with patch("ontology_hitl.api.dependencies.sparql_query") as m:
        yield m


@pytest.fixture
def mock_sparql_update():
    """Mock SPARQL update helper — patches both dependencies and routes.extend."""
    with patch("ontology_hitl.api.dependencies.sparql_update") as dep_mock, \
         patch("ontology_hitl.api.routes.extend.sparql_update") as route_mock:
        # Keep them in sync
        route_mock.side_effect = dep_mock.side_effect
        yield route_mock


@pytest.fixture
def mock_llm_generate():
    """Mock LLM generation — patches both dependencies and routes.extend."""
    with patch("ontology_hitl.api.dependencies.llm_generate") as dep_mock, \
         patch("ontology_hitl.api.routes.extend.llm_generate") as route_mock:
        route_mock.return_value = 'ex:TestClass a owl:Class ; rdfs:label "Test" .'
        dep_mock.return_value = 'ex:TestClass a owl:Class ; rdfs:label "Test" .'
        yield route_mock


@pytest.fixture
def mock_get_fuseki_client():
    """Mock Fuseki client."""
    with patch("ontology_hitl.api.dependencies.get_fuseki_client") as m:
        client = MagicMock()
        client.get.return_value.status_code = 200
        m.return_value = client
        yield m


@pytest.fixture
def mock_get_ollama_client():
    """Mock Ollama client."""
    with patch("ontology_hitl.api.dependencies.get_ollama_client") as m:
        client = MagicMock()
        client.get.return_value.status_code = 200
        m.return_value = client
        yield m
