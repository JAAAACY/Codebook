"""Tests for the rule-based business namer module."""

import pytest

from src.summarizer.business_namer import (
    infer_business_description,
    infer_business_name,
    infer_connection_verb,
    infer_function_explanation,
)


# ---------------------------------------------------------------------------
# infer_business_name
# ---------------------------------------------------------------------------

class TestInferBusinessName:
    """Test suite for infer_business_name."""

    def test_auth_module(self) -> None:
        assert infer_business_name("src/auth") == "认证系统"

    def test_plugins_module(self) -> None:
        assert infer_business_name("rust/crates/plugins") == "插件系统"

    def test_api_module(self) -> None:
        assert infer_business_name("rust/crates/api") == "API 接口"

    def test_db_module(self) -> None:
        assert infer_business_name("src/db") == "数据库"

    def test_cli_module(self) -> None:
        assert infer_business_name("src/cli") == "命令行工具"

    def test_runtime_module(self) -> None:
        assert infer_business_name("rust/crates/runtime") == "运行时引擎"

    def test_unknown_path_returns_non_empty(self) -> None:
        result = infer_business_name("some/totally/unknown_xyz_123")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_nested_path_uses_last_segment(self) -> None:
        """Nested paths should infer from the last directory segment."""
        result = infer_business_name("very/deep/nested/auth")
        assert result == "认证系统"

    def test_single_segment(self) -> None:
        result = infer_business_name("utils")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_trailing_slash_ignored(self) -> None:
        assert infer_business_name("src/auth/") == "认证系统"


# ---------------------------------------------------------------------------
# infer_business_description
# ---------------------------------------------------------------------------

class TestInferBusinessDescription:
    """Test suite for infer_business_description."""

    def test_with_function_names_login(self) -> None:
        desc = infer_business_description(
            module_name="auth",
            function_names=["login", "logout", "check_token"],
            class_names=[],
            file_count=3,
            line_count=200,
        )
        assert "登录" in desc or "认证" in desc

    def test_empty_module_returns_non_empty(self) -> None:
        desc = infer_business_description(
            module_name="empty_mod",
            function_names=[],
            class_names=[],
            file_count=0,
            line_count=0,
        )
        assert isinstance(desc, str)
        assert len(desc) > 0

    def test_with_class_names(self) -> None:
        desc = infer_business_description(
            module_name="models",
            function_names=[],
            class_names=["UserModel", "OrderModel"],
            file_count=2,
            line_count=150,
        )
        assert isinstance(desc, str)
        assert len(desc) > 0

    def test_description_includes_scale_info(self) -> None:
        desc = infer_business_description(
            module_name="core",
            function_names=["run", "start"],
            class_names=["Engine"],
            file_count=10,
            line_count=5000,
        )
        assert isinstance(desc, str)
        assert len(desc) > 0


# ---------------------------------------------------------------------------
# infer_function_explanation
# ---------------------------------------------------------------------------

class TestInferFunctionExplanation:
    """Test suite for infer_function_explanation."""

    def test_check_permission(self) -> None:
        explanation = infer_function_explanation(
            func_name="check_permission",
            params=["user_id", "action"],
            return_type="bool",
            docstring=None,
        )
        assert "检查" in explanation or "验证" in explanation

    def test_docstring_priority(self) -> None:
        """When docstring is provided, it should be used preferentially."""
        explanation = infer_function_explanation(
            func_name="do_something",
            params=[],
            return_type=None,
            docstring="执行数据备份操作",
        )
        assert "数据备份" in explanation

    def test_no_docstring_infer_from_prefix(self) -> None:
        explanation = infer_function_explanation(
            func_name="validate_email",
            params=["email"],
            return_type="bool",
            docstring=None,
        )
        assert "验证" in explanation or "校验" in explanation

    def test_get_prefix(self) -> None:
        explanation = infer_function_explanation(
            func_name="get_user",
            params=["user_id"],
            return_type="User",
            docstring=None,
        )
        assert "获取" in explanation

    def test_create_prefix(self) -> None:
        explanation = infer_function_explanation(
            func_name="create_order",
            params=["item_id", "quantity"],
            return_type="Order",
            docstring=None,
        )
        assert "创建" in explanation

    def test_delete_prefix(self) -> None:
        explanation = infer_function_explanation(
            func_name="delete_record",
            params=["record_id"],
            return_type=None,
            docstring=None,
        )
        assert "删除" in explanation

    def test_unknown_prefix_returns_non_empty(self) -> None:
        explanation = infer_function_explanation(
            func_name="xyz_unknown",
            params=[],
            return_type=None,
            docstring=None,
        )
        assert isinstance(explanation, str)
        assert len(explanation) > 0


# ---------------------------------------------------------------------------
# infer_connection_verb
# ---------------------------------------------------------------------------

class TestInferConnectionVerb:
    """Test suite for infer_connection_verb."""

    def test_to_db_module(self) -> None:
        verb = infer_connection_verb(
            from_module="service",
            to_module="db",
            call_count=5,
        )
        assert verb == "读写数据"

    def test_to_auth_module(self) -> None:
        verb = infer_connection_verb(
            from_module="api",
            to_module="auth",
            call_count=3,
        )
        assert verb == "验证权限"

    def test_default_verb(self) -> None:
        verb = infer_connection_verb(
            from_module="foo",
            to_module="bar",
            call_count=1,
        )
        assert verb == "调用"

    def test_to_cache_module(self) -> None:
        verb = infer_connection_verb(
            from_module="service",
            to_module="cache",
            call_count=10,
        )
        assert isinstance(verb, str)
        assert len(verb) > 0

    def test_to_logging_module(self) -> None:
        verb = infer_connection_verb(
            from_module="api",
            to_module="logging",
            call_count=20,
        )
        assert isinstance(verb, str)
        assert len(verb) > 0
