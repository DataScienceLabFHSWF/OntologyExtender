#!/usr/bin/env python3
"""Test script to verify W&B configuration and connectivity."""

import os
from ontology_hitl.core.config import Settings

def test_wandb_config():
    """Test W&B configuration loading."""
    settings = Settings()

    print("W&B Configuration:")
    print(f"  Enabled: {settings.wandb_enabled}")
    print(f"  Entity: {settings.wandb_entity}")
    print(f"  Project: {settings.wandb_project}")
    print(f"  API Key set: {bool(settings.wandb_api_key)}")

    if not settings.wandb_enabled:
        print("❌ W&B is disabled")
        return False

    if not settings.wandb_entity:
        print("❌ W&B entity not set")
        return False

    if not settings.wandb_api_key:
        print("❌ W&B API key not set")
        return False

    print("✅ W&B configuration looks good")

    # Test W&B import and basic functionality
    try:
        import wandb
        print("✅ W&B library imported successfully")

        # Test login
        wandb.login(key=settings.wandb_api_key)
        print("✅ W&B login successful")

        # Test basic init (but don't actually create a run)
        print("✅ W&B is ready to use")
        return True

    except ImportError:
        print("❌ W&B library not installed")
        return False
    except Exception as e:
        print(f"❌ W&B test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_wandb_config()
    exit(0 if success else 1)