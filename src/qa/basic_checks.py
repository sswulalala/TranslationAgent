import json
import os
import time

def check_chunk_quality(chunk_data, run_id="default"):
    """
    对单个 Chunk 进行质量检测。
    输入 chunk_data 结构示例:
    {
        "chunk_id": "1-003",
        "zh": "...", 
        "back_zh_to_en": "...", 
        "violations": [], 
        "meta": {...}
    }
    """
    # 1. 提取字段
    source_text = chunk_data.get('zh', '')
    target_text = chunk_data.get('back_zh_to_en', '')
    
    # 确保 violations 字段存在
    if 'violations' not in chunk_data:
        chunk_data['violations'] = []
    
    current_warnings = []
    
    # -------------------------------------------------------
    # 检查 1: 空输出
    # -------------------------------------------------------
    if not target_text or len(target_text.strip()) == 0:
        msg = "Critical: Empty translation output (back_zh_to_en is empty)."
        current_warnings.append(msg)
    
    # -------------------------------------------------------
    # 检查 2: 长度异常 (原文 zh vs 译文 back_zh_to_en)
    # -------------------------------------------------------
    src_len = len(source_text)
    tgt_len = len(target_text)
    
    # 只有当原文有一定长度时才检查，避免短句误报
    if src_len > 10:
        if tgt_len > src_len * 2.5: 
            msg = f"Suspicious length: Target ({tgt_len}) is > 2.5x Source ({src_len})."
            current_warnings.append(msg)
        elif tgt_len < src_len * 0.2: 
            msg = f"Suspicious length: Target ({tgt_len}) is < 0.2x Source ({src_len})."
            current_warnings.append(msg)

    # -------------------------------------------------------
    # 检查 3: 换行结构大幅丢失
    # -------------------------------------------------------
    src_paras = source_text.count('\n')
    tgt_paras = target_text.count('\n')
    
    # 容忍度设为 5，防止因为排版风格不同导致的误报
    if abs(src_paras - tgt_paras) > 5 and src_paras > 0:
         msg = f"Structure mismatch: Source has {src_paras} breaks, Target has {tgt_paras}."
         current_warnings.append(msg)

    # -------------------------------------------------------
    # 结果处理
    # -------------------------------------------------------
    if current_warnings:
        # A. 更新数据对象本身 (让后续流程知道出了问题)
        chunk_data['violations'].extend(current_warnings)
        
        # B. 写入磁盘日志 (方便事后排查)
        log_file = f"data/runs/{run_id}/warnings.jsonl"
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        # 尝试获取 chapter_id
        chap_id = "unknown"
        if 'meta' in chunk_data and 'chapter_id' in chunk_data['meta']:
            chap_id = chunk_data['meta']['chapter_id']
        elif 'chapter_id' in chunk_data:
            chap_id = chunk_data['chapter_id']

        record = {
            "timestamp": time.time(),
            "chunk_id": chunk_data.get('chunk_id'),
            "chapter_id": chap_id,
            "warnings": current_warnings,
            "preview_zh": source_text[:30],
            "preview_en": target_text[:30]
        }
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            
    return len(current_warnings) == 0

# ==========================================
# 测试代码 (__main__)
# ==========================================
if __name__ == "__main__":
    import shutil
    
    print("==========================================")
    print("🚀 开始测试: QA 模块 (适配新接口)")
    print("==========================================\n")

    TEST_RUN_ID = "test_qa_new_interface"
    LOG_PATH = f"data/runs/{TEST_RUN_ID}/warnings.jsonl"
    
    if os.path.exists(f"data/runs/{TEST_RUN_ID}"):
        shutil.rmtree(f"data/runs/{TEST_RUN_ID}")
    
    # 构造测试用例 (使用新的接口结构)
    test_cases = [
        {
            "desc": "✅ 正常情况",
            "data": {
                "chunk_id": "1-001",
                "zh": "这是一个正常的句子。\n包含两个段落。",
                "back_zh_to_en": "This is a normal sentence.\nIt contains two paragraphs.",
                "violations": [],
                "meta": {"chapter_id": 1}
            },
            "expect_pass": True
        },
        {
            "desc": "❌ 严重幻觉 (过长)",
            "data": {
                "chunk_id": "1-002",
                "zh": "短句。",
                "back_zh_to_en": "Repeat " * 50, # 恶意造长数据
                "violations": [],
                "meta": {"chapter_id": 1}
            },
            "expect_pass": False
        },
        {
            "desc": "❌ 空输出",
            "data": {
                "chunk_id": "1-003",
                "zh": "原文还在。",
                "back_zh_to_en": "", # 译文丢失
                "violations": [],
                "meta": {"chapter_id": 1}
            },
            "expect_pass": False
        }
    ]

    for case in test_cases:
        print(f"测试: {case['desc']}")
        chunk_obj = case['data']
        
        # 调用函数 (注意现在只传 chunk_obj)
        is_passed = check_chunk_quality(chunk_obj, run_id=TEST_RUN_ID)
        
        # 验证返回值
        if is_passed == case['expect_pass']:
            print(f"  -> 状态检查: 符合预期 (Pass={is_passed})")
        else:
            print(f"  -> ⚠️ 状态检查失败: 预期 {case['expect_pass']} 实际 {is_passed}")
            
        # 验证 violations 字段是否被更新
        if not is_passed:
            print(f"  -> Violations 列表内容: {chunk_obj['violations']}")
            if len(chunk_obj['violations']) > 0:
                print("  -> ✅ 数据对象被正确更新")
            else:
                print("  -> ❌ 错误: violations 列表未被填充")
        
        print("-" * 30)

    # 验证日志文件
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, 'r', encoding='utf-8') as f:
            count = len(f.readlines())
            print(f"\n📄 日志文件生成成功，共 {count} 条警告记录 (预期 2 条)。")
    else:
        print("\n❌ 日志文件未生成！")