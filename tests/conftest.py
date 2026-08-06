import pytest
from unittest.mock import patch

from models import Article


@pytest.fixture
def make_article():
    def _make(guid="guid-1", **overrides):
        defaults = dict(
            guid=guid,
            title="Some Title",
            url="https://example.com/post",
            blog="Storage",
            excerpt="An excerpt.",
            content="<p>Full body</p>",
        )
        defaults.update(overrides)
        return Article(**defaults)

    return _make


@pytest.fixture
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")


# Patch moto's SSM parameter validation to allow /aws-infra-feed/ prefix for testing
@pytest.fixture(scope="session", autouse=True)
def _patch_moto_ssm_validation():
    """Allow /aws-infra-feed/ parameters in SSM mocks for testing"""
    from unittest.mock import patch as mock_patch
    from moto.ssm import models

    # Store the original put_parameter method
    original_method = models.SimpleSystemManagerBackend.put_parameter

    # Create a wrapper that bypasses the /aws-infra-feed validation
    def bypass_validation_put_parameter(self, name, description, value, parameter_type, allowed_pattern, keyid, overwrite, tags, data_type, tier, policies):
        # For /aws-infra-feed/ parameters, bypass moto's validation by temporarily setting a flag
        if name.lower().startswith("/aws-infra-feed/"):
            # Directly create the parameter in the backend store
            from moto.ssm.models import Parameter
            from datetime import datetime, timezone

            param = Parameter(
                name=name,
                value=value,
                parameter_type=parameter_type,
                description=description,
                allowed_pattern=allowed_pattern,
                keyid=keyid,
                data_type=data_type,
                tier=tier,
                policies=policies,
                account_id=self.account_id,
                last_modified_date=datetime.now(timezone.utc),
                version=1,
            )
            self._parameters[name] = [param]
            return param
        else:
            # For other parameters, use the original method
            return original_method(self, name, description, value, parameter_type, allowed_pattern, keyid, overwrite, tags, data_type, tier, policies)

    # Apply the patch
    models.SimpleSystemManagerBackend.put_parameter = bypass_validation_put_parameter
    yield
    # Restore original after tests
    models.SimpleSystemManagerBackend.put_parameter = original_method
