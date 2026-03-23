"""Role system v0.3 tests — 验证三视图系统（dev/pm/domain_expert）和后向兼容性。"""

import json
import pytest

from src.summarizer.engine import (
    _normalize_role,
    _get_banned_terms,
    _get_role_guidance,
    _load_codebook_config,
)


class TestRoleNormalization:
    """测试旧角色名到新视图的映射。"""

    def test_pm_maps_to_pm(self):
        """PM 角色直接对应 pm 视图。"""
        assert _normalize_role("pm") == "pm"

    def test_ceo_maps_to_pm(self):
        """CEO 角色映射到 pm 视图。"""
        assert _normalize_role("ceo") == "pm"

    def test_investor_maps_to_pm(self):
        """投资人角色映射到 pm 视图。"""
        assert _normalize_role("investor") == "pm"

    def test_qa_maps_to_dev(self):
        """QA 角色映射到 dev 视角（关注边界条件）。"""
        assert _normalize_role("qa") == "dev"

    def test_dev_maps_to_dev(self):
        """Dev 角色直接对应 dev 视图。"""
        assert _normalize_role("dev") == "dev"

    def test_domain_expert_maps_to_domain_expert(self):
        """domain_expert 角色直接对应 domain_expert 视图。"""
        assert _normalize_role("domain_expert") == "domain_expert"

    def test_invalid_role_defaults_to_pm(self):
        """无效的角色名回退到 pm（默认值）。"""
        assert _normalize_role("invalid_role_xyz") == "pm"

    def test_case_sensitive(self):
        """角色名应该区分大小写（全部小写）。"""
        # CEO (大写) 应该映射失败，回退到 pm
        assert _normalize_role("CEO") == "pm"
        assert _normalize_role("Dev") == "pm"  # 应该回退


class TestBannedTerms:
    """测试禁用术语在不同角色中的处理。"""

    def test_pm_gets_banned_terms(self):
        """PM 视角应该获取禁用术语表。"""
        terms = _get_banned_terms(role="pm")
        assert len(terms) > 0
        # 检查常见禁用术语
        assert "幂等" in terms or "idempotent" in terms
        assert "slug" in terms or "URL" in terms

    def test_dev_gets_no_banned_terms(self):
        """Dev 视角不应该有禁用术语（开发者可以用所有技术术语）。"""
        terms = _get_banned_terms(role="dev")
        assert terms == ""

    def test_domain_expert_gets_banned_terms(self):
        """domain_expert 视角应该也受禁用术语限制（保持一致）。"""
        terms = _get_banned_terms(role="domain_expert")
        # domain_expert 类似 PM，也有禁用术语
        assert len(terms) > 0

    def test_banned_terms_without_role(self):
        """未指定角色时，默认按 PM 视角处理。"""
        terms_default = _get_banned_terms()
        terms_pm = _get_banned_terms(role="pm")
        assert terms_default == terms_pm

    def test_banned_terms_includes_format(self):
        """禁用术语应该包含「术语 → 业务语言」的格式。"""
        terms = _get_banned_terms(role="pm")
        # 检查至少有一个箭头
        assert "→" in terms


class TestRoleGuidance:
    """测试不同角色和领域的 guidance 文本。"""

    def test_dev_guidance_exists(self):
        """Dev 角色应该有对应的 guidance。"""
        guidance = _get_role_guidance("dev")
        assert len(guidance) > 0
        assert "开发者" in guidance or "developer" in guidance

    def test_pm_guidance_exists(self):
        """PM 角色应该有对应的 guidance。"""
        guidance = _get_role_guidance("pm")
        assert len(guidance) > 0
        assert "产品经理" in guidance or "PM" in guidance or "manager" in guidance

    def test_domain_expert_guidance_exists(self):
        """domain_expert 角色应该有对应的 guidance。"""
        guidance = _get_role_guidance("domain_expert")
        assert len(guidance) > 0
        assert "行业专家" in guidance or "domain" in guidance

    def test_domain_expert_fintech_guidance(self):
        """domain_expert 角色在金融领域应该有特定的 guidance。"""
        guidance = _get_role_guidance("domain_expert", project_domain="fintech")
        assert len(guidance) > 0
        # 金融领域应该包含金融术语
        assert "KYC" in guidance or "AML" in guidance or "支付" in guidance or "合规" in guidance

    def test_domain_expert_healthcare_guidance(self):
        """domain_expert 角色在医疗领域应该有特定的 guidance。"""
        guidance = _get_role_guidance("domain_expert", project_domain="healthcare")
        assert len(guidance) > 0
        # 医疗领域应该包含医疗术语
        assert "FHIR" in guidance or "患者" in guidance or "诊断" in guidance or "隐私" in guidance

    def test_domain_expert_ecommerce_guidance(self):
        """domain_expert 角色在电商领域应该有特定的 guidance。"""
        guidance = _get_role_guidance("domain_expert", project_domain="ecommerce")
        assert len(guidance) > 0
        # 电商领域应该包含电商术语
        assert "订单" in guidance or "支付" in guidance or "库存" in guidance or "退款" in guidance

    def test_domain_expert_unknown_domain_fallback(self):
        """domain_expert 角色在未知领域应该回退到通用 guidance。"""
        guidance = _get_role_guidance("domain_expert", project_domain="unknown_domain")
        assert len(guidance) > 0
        # 应该回退到通用的 domain_expert guidance
        assert "行业专家" in guidance or "domain" in guidance


class TestConfigLoading:
    """测试配置文件的加载和结构。"""

    def test_config_v0_3_exists(self):
        """Config v0.3 应该被加载。"""
        config = _load_codebook_config()
        assert config is not None
        assert len(config) > 0

    def test_config_has_role_system(self):
        """Config 应该包含 role_system_v0_3 部分。"""
        config = _load_codebook_config()
        assert "role_system_v0_3" in config

    def test_config_has_three_views(self):
        """Role system 应该定义三个视图。"""
        config = _load_codebook_config()
        views = config.get("role_system_v0_3", {}).get("views", [])
        assert len(views) == 3
        view_names = [v.get("name") for v in views]
        assert "dev" in view_names
        assert "pm" in view_names
        assert "domain_expert" in view_names

    def test_config_has_backward_compat_mappings(self):
        """Config 应该包含向后兼容映射。"""
        config = _load_codebook_config()
        mappings = config.get("backward_compatibility", {}).get("mappings", {})
        assert "ceo" in mappings
        assert "pm" in mappings
        assert "investor" in mappings
        assert "qa" in mappings

    def test_config_mapping_correctness(self):
        """验证向后兼容映射的正确性。"""
        config = _load_codebook_config()
        mappings = config.get("backward_compatibility", {}).get("mappings", {})
        assert mappings["ceo"] == "pm"
        assert mappings["investor"] == "pm"
        assert mappings["qa"] == "dev"
        assert mappings["pm"] == "pm"
        assert mappings["dev"] == "dev"

    def test_config_has_domain_inference_rules(self):
        """Config 应该包含领域推断规则。"""
        config = _load_codebook_config()
        inference = config.get("project_domain_inference", {})
        assert "priority_layers" in inference
        assert len(inference["priority_layers"]) >= 3

    def test_config_domains_have_markers(self):
        """各个领域应该有识别标记。"""
        config = _load_codebook_config()
        layers = config.get("project_domain_inference", {}).get("priority_layers", [])
        inference_rules = None
        for layer in layers:
            if layer.get("name") == "自动推断":
                inference_rules = layer.get("inference_rules", {})
                break

        assert inference_rules is not None
        assert "fintech" in inference_rules
        assert "healthcare" in inference_rules
        assert "ecommerce" in inference_rules

    def test_config_fintech_has_keywords(self):
        """金融领域应该有关键词和依赖标记。"""
        config = _load_codebook_config()
        layers = config.get("project_domain_inference", {}).get("priority_layers", [])
        for layer in layers:
            if layer.get("name") == "自动推断":
                fintech_rules = layer.get("inference_rules", {}).get("fintech", {})
                assert len(fintech_rules.get("readme_keywords", [])) > 0
                assert len(fintech_rules.get("dependency_markers", [])) > 0


class TestGuidanceCompletion:
    """测试 guidance 的内容完整性。"""

    def test_dev_guidance_mentions_code(self):
        """Dev guidance 应该强调代码细节。"""
        guidance = _get_role_guidance("dev")
        # 应该提到代码相关的关键信息
        assert any(word in guidance for word in ["代码", "函数", "signature", "细节", "实现"])

    def test_pm_guidance_mentions_business(self):
        """PM guidance 应该强调业务影响和风险。"""
        guidance = _get_role_guidance("pm")
        # 应该提到业务相关的关键信息
        assert any(word in guidance for word in ["业务", "功能", "风险", "影响", "估算"])

    def test_domain_expert_guidance_mentions_rules(self):
        """domain_expert guidance 应该强调规则和合规。"""
        guidance = _get_role_guidance("domain_expert")
        # 应该提到规则和合规相关的关键信息
        assert any(word in guidance for word in ["规则", "合规", "风险", "审计", "标准"])

    def test_fintech_guidance_mentions_kycaml(self):
        """金融 guidance 应该提到 KYC 和 AML。"""
        guidance = _get_role_guidance("domain_expert", project_domain="fintech")
        # 至少提到一个金融关键术语
        assert "KYC" in guidance or "AML" in guidance or "交易" in guidance

    def test_healthcare_guidance_mentions_patient(self):
        """医疗 guidance 应该提到患者和隐私。"""
        guidance = _get_role_guidance("domain_expert", project_domain="healthcare")
        # 至少提到医疗关键概念
        assert "患者" in guidance or "FHIR" in guidance or "隐私" in guidance or "诊断" in guidance

    def test_ecommerce_guidance_mentions_order(self):
        """电商 guidance 应该提到订单和库存。"""
        guidance = _get_role_guidance("domain_expert", project_domain="ecommerce")
        # 至少提到电商关键概念
        assert "订单" in guidance or "库存" in guidance or "支付" in guidance or "退款" in guidance


class TestRoleConsistency:
    """测试角色系统的一致性。"""

    def test_all_roles_have_guidance(self):
        """所有有效角色都应该有 guidance。"""
        valid_roles = ["dev", "pm", "domain_expert"]
        for role in valid_roles:
            guidance = _get_role_guidance(role)
            assert len(guidance) > 0, f"Role {role} has no guidance"

    def test_role_normalization_is_idempotent(self):
        """角色规范化应该是幂等的（规范化两次结果相同）。"""
        test_roles = ["ceo", "pm", "investor", "qa", "dev", "domain_expert"]
        for role in test_roles:
            normalized_once = _normalize_role(role)
            normalized_twice = _normalize_role(normalized_once)
            assert normalized_once == normalized_twice, f"Role {role} normalization is not idempotent"

    def test_backward_compat_covers_all_old_roles(self):
        """向后兼容映射应该覆盖所有旧角色名。"""
        config = _load_codebook_config()
        mappings = config.get("backward_compatibility", {}).get("mappings", {})
        old_roles = ["ceo", "investor", "qa"]
        for role in old_roles:
            assert role in mappings, f"Old role {role} not in backward compat mappings"

    def test_all_mapped_roles_are_valid(self):
        """所有映射到的角色都应该是有效的。"""
        config = _load_codebook_config()
        mappings = config.get("backward_compatibility", {}).get("mappings", {})
        valid_views = {"dev", "pm", "domain_expert"}
        for old_role, new_role in mappings.items():
            assert new_role in valid_views, f"Role {old_role} maps to invalid view {new_role}"


class TestDomainExpertSpecifics:
    """测试 domain_expert 视角的特定功能。"""

    def test_domain_expert_requires_project_domain(self):
        """domain_expert 视图的定义中应该标记 requires_project_domain。"""
        config = _load_codebook_config()
        views = config.get("role_system_v0_3", {}).get("views", [])
        domain_expert = next((v for v in views if v["name"] == "domain_expert"), None)
        assert domain_expert is not None
        assert domain_expert.get("requires_project_domain") is True

    def test_domain_expert_has_supported_domains(self):
        """domain_expert 视图应该列出支持的领域。"""
        config = _load_codebook_config()
        views = config.get("role_system_v0_3", {}).get("views", [])
        domain_expert = next((v for v in views if v["name"] == "domain_expert"), None)
        domains = domain_expert.get("supported_domains", [])
        assert "fintech" in domains
        assert "healthcare" in domains
        assert "ecommerce" in domains

    def test_domain_expert_guidance_for_all_domains(self):
        """所有支持的领域都应该有 guidance。"""
        config = _load_codebook_config()
        views = config.get("role_system_v0_3", {}).get("views", [])
        domain_expert = next((v for v in views if v["name"] == "domain_expert"), None)
        domains = domain_expert.get("supported_domains", [])

        for domain in domains:
            if domain != "general":
                guidance = _get_role_guidance("domain_expert", project_domain=domain)
                assert len(guidance) > 0, f"No guidance for domain {domain}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
