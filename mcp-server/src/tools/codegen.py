"""codegen — 代码生成工具：自然语言指令 → unified diff + 业务语言解释。

完整流程:
1. 接收用户自然语言指令 + locate 定位结果
2. 从仓库读取被定位到的源文件完整内容
3. 组装 prompt（三层结构：system + context + user）
4. 调用 LLM 生成变更方案
5. 解析输出为结构化 CodegenResult
6. 验证 diff 可直接 git apply
7. 返回：unified diff + 变更摘要 + 影响范围 + 验证步骤

错误处理:
- 文件读取失败 → 提示文件路径可能不正确
- LLM 返回格式不对 → 重试一次，附带格式示例
- diff 无法 apply → 自动修复行号偏移，或回退为手工补丁
"""

from __future__ import annotations

import structlog

from src.tools.codegen_engine import CodegenEngine

logger = structlog.get_logger()


async def codegen(
    instruction: str,
    repo_path: str,
    locate_result: dict | None = None,
    file_paths: list[str] | None = None,
    role: str = "pm",
) -> dict:
    """根据自然语言指令生成代码变更。

    Args:
        instruction: 用户的自然语言修改指令，如「把注册报错改成中文」。
        repo_path: 本地仓库路径（已 clone 的路径）。
        locate_result: locate/diagnose 阶段的输出字典。
            如果为 None，则需要 file_paths 参数指定要修改的文件。
        file_paths: 要修改的文件路径列表（相对于 repo_path）。
            与 locate_result 互补：locate_result 优先，file_paths 作为补充或 fallback。
        role: 目标角色，决定输出的语言风格。

    Returns:
        {
            "status": "success" | "partial" | "error",
            "change_summary": [...],      # 业务语言变更摘要
            "unified_diff": "...",         # 完整 unified diff（可直接 git apply）
            "diff_blocks": [...],          # 分文件的 diff 块
            "blast_radius": [...],         # 影响范围
            "verification_steps": [...],   # 验证步骤
            "diff_valid": bool,            # diff 是否通过 apply 验证
            "validation_detail": "...",    # 验证详情
            "raw_llm_output": "...",       # 原始 LLM 输出
        }
    """
    logger.info(
        "codegen called",
        instruction=instruction[:100],
        repo_path=repo_path,
        has_locate=locate_result is not None,
        file_paths=file_paths,
        role=role,
    )

    engine = CodegenEngine(repo_path=repo_path)

    try:
        result = await engine.run(
            instruction=instruction,
            locate_result=locate_result,
            file_paths=file_paths,
            role=role,
        )
        return result
    except Exception as e:
        logger.error("codegen failed", error=str(e), exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "change_summary": [],
            "unified_diff": "",
            "diff_blocks": [],
            "blast_radius": [],
            "verification_steps": [],
            "diff_valid": False,
            "validation_detail": f"引擎执行失败: {e}",
            "raw_llm_output": "",
        }
