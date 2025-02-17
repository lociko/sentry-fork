import uuid
from unittest import mock

import pytest

from sentry.constants import ObjectStatus
from sentry.models.rule import Rule, RuleSource
from sentry.testutils.helpers.data_blobs import GITHUB_ACTION_DATA_BLOBS
from sentry.workflow_engine.handlers.action.notification.issue_alert import (
    BaseIssueAlertHandler,
    DiscordIssueAlertHandler,
    MSTeamsIssueAlertHandler,
    OpsgenieIssueAlertHandler,
    PagerDutyIssueAlertHandler,
    SlackIssueAlertHandler,
    TicketingIssueAlertHandler,
)
from sentry.workflow_engine.models import Action
from sentry.workflow_engine.types import WorkflowJob
from sentry.workflow_engine.typings.notification_action import (
    ACTION_FIELD_MAPPINGS,
    EXCLUDED_ACTION_DATA_KEYS,
    ActionFieldMapping,
    ActionFieldMappingKeys,
)
from tests.sentry.workflow_engine.test_base import BaseWorkflowTest


def pop_keys_from_data_blob(data_blob: dict, action_type: Action.Type) -> dict:
    """
    Remove standard action fields from each dictionary in the data blob.

    Args:
        data_blob: List of dictionaries containing action data

    Returns:
        List of dictionaries with standard action fields removed
    """
    KEYS_TO_REMOVE = {
        *EXCLUDED_ACTION_DATA_KEYS,
        ACTION_FIELD_MAPPINGS[action_type].get(ActionFieldMappingKeys.INTEGRATION_ID_KEY.value),
        ACTION_FIELD_MAPPINGS[action_type].get(ActionFieldMappingKeys.TARGET_IDENTIFIER_KEY.value),
        ACTION_FIELD_MAPPINGS[action_type].get(ActionFieldMappingKeys.TARGET_DISPLAY_KEY.value),
    }

    return {k: v for k, v in data_blob.items() if k not in KEYS_TO_REMOVE}


class TestBaseIssueAlertHandler(BaseWorkflowTest):
    def setUp(self):
        super().setUp()
        self.project = self.create_project()
        self.detector = self.create_detector(project=self.project)
        self.workflow = self.create_workflow(environment=self.environment)
        self.action = self.create_action(
            type=Action.Type.DISCORD,
            integration_id="1234567890",
            target_identifier="channel456",
            data={"tags": "environment,user,my_tag"},
        )
        self.group, self.event, self.group_event = self.create_group_event()
        self.job = WorkflowJob(event=self.group_event, workflow=self.workflow)

        class TestHandler(BaseIssueAlertHandler):
            @classmethod
            def get_additional_fields(cls, action: Action, mapping: ActionFieldMapping):
                return {"tags": "environment,user,my_tag"}

            @classmethod
            def get_target_display(cls, action: Action, mapping: ActionFieldMapping):
                return {}

        self.handler = TestHandler()

    def test_create_rule_instance_from_action_missing_properties_raises_value_error(self):
        class TestHandler(BaseIssueAlertHandler):
            @classmethod
            def get_additional_fields(cls, action: Action, mapping: ActionFieldMapping):
                return {"tags": "environment,user,my_tag"}

        handler = TestHandler()
        with pytest.raises(ValueError):
            handler.create_rule_instance_from_action(self.action, self.detector, self.job)

    def test_create_rule_instance_from_action(self):
        """Test that create_rule_instance_from_action creates a Rule with correct attributes"""
        rule = self.handler.create_rule_instance_from_action(self.action, self.detector, self.job)

        assert isinstance(rule, Rule)
        assert rule.id == self.action.id
        assert rule.project == self.detector.project
        assert rule.environment_id is not None
        assert self.workflow.environment is not None
        assert rule.environment_id == self.workflow.environment.id
        assert rule.label == self.detector.name
        assert rule.data == {
            "actions": [
                {
                    "id": "sentry.integrations.discord.notify_action.DiscordNotifyServiceAction",
                    "server": "1234567890",
                    "channel_id": "channel456",
                    "tags": "environment,user,my_tag",
                }
            ]
        }
        assert rule.status == ObjectStatus.ACTIVE
        assert rule.source == RuleSource.ISSUE

    def test_create_rule_instance_from_action_missing_action_properties_raises_value_error(self):
        action = self.create_action(type=Action.Type.DISCORD)
        with pytest.raises(ValueError):
            self.handler.create_rule_instance_from_action(action, self.detector, self.job)

    def test_create_rule_instance_from_action_no_environment(self):
        """Test that create_rule_instance_from_action creates a Rule with correct attributes"""
        workflow = self.create_workflow()
        job = WorkflowJob(event=self.group_event, workflow=workflow)
        rule = self.handler.create_rule_instance_from_action(self.action, self.detector, job)

        assert isinstance(rule, Rule)
        assert rule.id == self.action.id
        assert rule.project == self.detector.project
        assert rule.environment_id is None
        assert rule.label == self.detector.name
        assert rule.data == {
            "actions": [
                {
                    "id": "sentry.integrations.discord.notify_action.DiscordNotifyServiceAction",
                    "server": "1234567890",
                    "channel_id": "channel456",
                    "tags": "environment,user,my_tag",
                }
            ]
        }
        assert rule.status == ObjectStatus.ACTIVE
        assert rule.source == RuleSource.ISSUE

    @mock.patch("sentry.workflow_engine.handlers.action.notification.issue_alert.safe_execute")
    @mock.patch(
        "sentry.workflow_engine.handlers.action.notification.issue_alert.activate_downstream_actions"
    )
    @mock.patch("uuid.uuid4")
    def test_invoke_legacy_registry(
        self, mock_uuid, mock_activate_downstream_actions, mock_safe_execute
    ):
        # Test that invoke_legacy_registry correctly processes the action
        mock_uuid.return_value = uuid.UUID("12345678-1234-5678-1234-567812345678")

        # Mock callback and futures
        mock_callback = mock.Mock()
        mock_futures = [mock.Mock()]
        mock_activate_downstream_actions.return_value = {"some_key": (mock_callback, mock_futures)}

        self.handler.invoke_legacy_registry(self.job, self.action, self.detector)

        # Verify activate_downstream_actions called with correct args
        mock_activate_downstream_actions.assert_called_once_with(
            mock.ANY, self.job["event"], "12345678-1234-5678-1234-567812345678"  # Rule instance
        )

        # Verify callback execution
        mock_safe_execute.assert_called_once_with(mock_callback, self.job["event"], mock_futures)


class TestDiscordIssueAlertHandler(BaseWorkflowTest):
    def setUp(self):
        super().setUp()
        self.handler = DiscordIssueAlertHandler()
        self.action = self.create_action(
            type=Action.Type.DISCORD,
            integration_id="1234567890",
            target_identifier="channel456",
            data={"tags": "environment,user,my_tag"},
        )
        # self.project = self.create_project()
        # self.detector = self.create_detector(project=self.project)
        # self.group, self.event, self.group_event = self.create_group_event()
        # self.job = WorkflowJob(event=self.group_event)

    def test_build_rule_action_blob(self):
        """Test that build_rule_action_blob creates correct Discord action data"""
        blob = self.handler.build_rule_action_blob(self.action)

        assert blob == {
            "id": "sentry.integrations.discord.notify_action.DiscordNotifyServiceAction",
            "server": "1234567890",
            "channel_id": "channel456",
            "tags": "environment,user,my_tag",
        }

    def test_build_rule_action_blob_no_tags(self):
        """Test that build_rule_action_blob handles missing tags"""
        self.action.data = {}
        blob = self.handler.build_rule_action_blob(self.action)

        assert blob == {
            "id": "sentry.integrations.discord.notify_action.DiscordNotifyServiceAction",
            "server": "1234567890",
            "channel_id": "channel456",
            "tags": "",
        }


class TestMSTeamsIssueAlertHandler(BaseWorkflowTest):
    def setUp(self):
        super().setUp()
        self.handler = MSTeamsIssueAlertHandler()
        self.action = self.create_action(
            type=Action.Type.MSTEAMS,
            integration_id="1234567890",
            target_identifier="channel789",
            target_display="General Channel",
        )

    def test_build_rule_action_blob(self):
        """Test that build_rule_action_blob creates correct MSTeams action data"""
        blob = self.handler.build_rule_action_blob(self.action)

        assert blob == {
            "id": "sentry.integrations.msteams.notify_action.MsTeamsNotifyServiceAction",
            "team": "1234567890",
            "channel_id": "channel789",
            "channel": "General Channel",
        }


class TestSlackIssueAlertHandler(BaseWorkflowTest):
    def setUp(self):
        super().setUp()
        self.handler = SlackIssueAlertHandler()
        self.action = self.create_action(
            type=Action.Type.SLACK,
            integration_id="1234567890",
            target_identifier="channel789",
            target_display="#general",
            data={"tags": "environment,user", "notes": "Important alert"},
        )

    def test_build_rule_action_blob(self):
        """Test that build_rule_action_blob creates correct Slack action data"""
        blob = self.handler.build_rule_action_blob(self.action)

        assert blob == {
            "id": "sentry.integrations.slack.notify_action.SlackNotifyServiceAction",
            "workspace": "1234567890",
            "channel_id": "channel789",
            "channel": "#general",
            "tags": "environment,user",
            "notes": "Important alert",
        }

    def test_build_rule_action_blob_no_data(self):
        """Test that build_rule_action_blob handles missing data"""
        self.action.data = {}
        blob = self.handler.build_rule_action_blob(self.action)

        assert blob == {
            "id": "sentry.integrations.slack.notify_action.SlackNotifyServiceAction",
            "workspace": "1234567890",
            "channel_id": "channel789",
            "channel": "#general",
            "tags": "",
            "notes": "",
        }


class TestPagerDutyIssueAlertHandler(BaseWorkflowTest):
    def setUp(self):
        super().setUp()
        self.handler = PagerDutyIssueAlertHandler()
        self.action = self.create_action(
            type=Action.Type.PAGERDUTY,
            integration_id="1234567890",
            target_identifier="service789",
            data={"priority": "P1"},
        )

    def test_build_rule_action_blob(self):
        """Test that build_rule_action_blob creates correct PagerDuty action data"""
        blob = self.handler.build_rule_action_blob(self.action)

        assert blob == {
            "id": "sentry.integrations.pagerduty.notify_action.PagerDutyNotifyServiceAction",
            "account": "1234567890",
            "service": "service789",
            "severity": "P1",
        }

    def test_build_rule_action_blob_no_priority(self):
        """Test that build_rule_action_blob handles missing priority"""
        self.action.data = {}
        blob = self.handler.build_rule_action_blob(self.action)

        assert blob == {
            "id": "sentry.integrations.pagerduty.notify_action.PagerDutyNotifyServiceAction",
            "account": "1234567890",
            "service": "service789",
            "severity": "",
        }


class TestOpsgenieIssueAlertHandler(BaseWorkflowTest):
    def setUp(self):
        super().setUp()
        self.handler = OpsgenieIssueAlertHandler()
        self.action = self.create_action(
            type=Action.Type.OPSGENIE,
            integration_id="1234567890",
            target_identifier="team789",
            data={"priority": "P1"},
        )

    def test_build_rule_action_blob(self):
        """Test that build_rule_action_blob creates correct Opsgenie action data"""
        blob = self.handler.build_rule_action_blob(self.action)

        assert blob == {
            "id": "sentry.integrations.opsgenie.notify_action.OpsgenieNotifyTeamAction",
            "account": "1234567890",
            "team": "team789",
            "priority": "P1",
        }

    def test_build_rule_action_blob_no_priority(self):
        """Test that build_rule_action_blob handles missing priority"""
        self.action.data = {}
        blob = self.handler.build_rule_action_blob(self.action)

        assert blob == {
            "id": "sentry.integrations.opsgenie.notify_action.OpsgenieNotifyTeamAction",
            "account": "1234567890",
            "team": "team789",
            "priority": "",
        }


class TestGithubIssueAlertHandler(BaseWorkflowTest):
    def setUp(self):
        super().setUp()
        self.handler = TicketingIssueAlertHandler()

    def test_build_rule_action_blob(self):
        """Test that build_rule_action_blob creates correct Github action data"""
        for expected in GITHUB_ACTION_DATA_BLOBS:
            action_data = pop_keys_from_data_blob(expected, Action.Type.GITHUB)

            action = self.create_action(
                type=Action.Type.GITHUB,
                integration_id=expected["integration"],
                data=action_data,
            )

            blob = self.handler.build_rule_action_blob(action)

            assert blob == {
                "id": expected["id"],
                "integration": expected["integration"],
                **blob,
            }
