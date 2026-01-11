import re
import os
import json


def split_text_into_chunks(text, chapter_id, max_chars=1500, min_chars=800):
    """
    将文本按段落分组切分为 Chunk，适配接口 { "chapter_id": 1, "chunk_id": "1-003", ... }
    """
    # 1. 预处理
    paragraphs = text.split('\n') 
    
    chunks = []
    current_chunk_text = []
    current_length = 0
    para_start_index = 0
    
    # 内部计数器，用于生成 000, 001, 002
    chunk_counter = 0

    for i, para in enumerate(paragraphs):
        para_len = len(para)
        
        # 策略：累积长度超过上限 且 当前块已有一定长度 -> 切分
        if (current_length + para_len > max_chars) and (current_length > min_chars):
            
            # 生成格式如 "1-000", "1-001" 的字符串
            chunk_str_id = f"{chapter_id}-{chunk_counter:03d}"
            
            # 封包当前 Chunk
            chunk_data = {
                "chapter_id": chapter_id,
                "chunk_id": chunk_str_id, 
                "text": "\n".join(current_chunk_text),
                "para_start": para_start_index,
                "para_end": i - 1,
                "source_token_count": current_length,
                
                # --- 上下文占位符 ---
                "prev_summary": "", # 占位：等待 Workflow 填入上一块的摘要
                "prev_tail": ""     # 占位：等待 Workflow 填入上一块的末尾原文/译文
            }
            chunks.append(chunk_data)
            
            # 重置
            chunk_counter += 1
            current_chunk_text = []
            current_length = 0
            para_start_index = i
            
        current_chunk_text.append(para)
        current_length += para_len + 1 

    # 处理最后一个尾部 Chunk
    if current_chunk_text:
        chunk_str_id = f"{chapter_id}-{chunk_counter:03d}"
        
        chunk_data = {
            "chapter_id": chapter_id,
            "chunk_id": chunk_str_id,
            "text": "\n".join(current_chunk_text),
            "para_start": para_start_index,
            "para_end": len(paragraphs) - 1,
            "source_token_count": current_length,
            "prev_summary": "", # 占位
            "prev_tail": ""     # 占位
        }
        chunks.append(chunk_data)

    return chunks


def build_context_payload(prev_translation, window_size=3):
    """
    从上一块的【译文】中提取末尾 N 句，作为当前块的 Context。
    window_size: 提取最后几句话

    在 Workflow 中的使用：
    context_tail = build_context_payload(last_translation, window_size=3)
    chunk['prev_tail'] = context_tail
    """
    if not prev_translation:
        return ""
    
    sentences = re.split(r'(?<=[。！？])', prev_translation)
    # 过滤空字符串
    sentences = [s.strip() for s in sentences if s.strip()]
    
    # 取最后 N 句
    context_sentences = sentences[-window_size:]
    
    return "".join(context_sentences)

# 在 Workflow 中的使用：
# context_tail = build_context_payload(last_translation, window_size=3)
# chunk['prev_tail'] = context_tail



if __name__ == "__main__":
    file_path = 'data/processed/诡秘之主_final.jsonl'
    
    print(f"🚀 开始读取测试数据: {file_path}")
    
    if not os.path.exists(file_path):
        print(f"❌ 错误: 文件不存在，请检查路径: {file_path}")
    
    # 计数器
    total_chapters = 0
    total_chunks = 0
    passed_count = 0
    
    # 逐行读取 JSONL
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            
            try:
                data = json.loads(line)
                
                original_text = data.get('text')
                chapter_title = data.get('title', f'Chapter_{line_num}')
                chapter_id = data.get('chapter_index', line_num)

                if original_text is None:
                    print(f"⚠️ 跳过第 {line_num} 行: 未找到文本内容字段")
                    continue

                total_chapters += 1

                # --- 执行切分 ---
                # 设定参数：比如每 1000 字切一段
                chunks = split_text_into_chunks(original_text, chapter_id, max_chars=1000, min_chars=500)
                print(chunks)
                
                total_chunks += len(chunks)

                # --- 核心验证：还原测试 (Reconstruction Test) ---
                # 将所有 Chunk 的 text 拼回去，检查是否等于原文
                # 因为你的函数内部用 split('\n') 和 join('\n')，所以这里用 join('\n') 还原
                reconstructed_text = "\n".join([c['text'] for c in chunks])
                
                if reconstructed_text == original_text:
                    # 只有在失败时才打印，或者每隔 10 章打印一次成功信息，避免刷屏
                    if total_chapters % 10 == 0:
                        print(f"✅ [Pass] {chapter_title}: 切分为 {len(chunks)} 块 (原文长度 {len(original_text)})")
                    passed_count += 1
                else:
                    print(f"❌ [FAIL] {chapter_title}: 还原后与原文不一致！")
                    print(f"   原文长度: {len(original_text)} vs 还原长度: {len(reconstructed_text)}")

            except json.JSONDecodeError:
                print(f"❌ 第 {line_num} 行 JSON 解析失败")
            except Exception as e:
                print(f"❌ 处理章节 '{chapter_title}' 时发生未知错误: {e}")

    print("\n" + "="*30)
    print("📊 测试统计报告")
    print("="*30)
    print(f"处理章节数: {total_chapters}")
    print(f"生成 Chunk数: {total_chunks}")
    print(f"平均每章 Chunk: {total_chunks / total_chapters if total_chapters else 0:.1f}")
    print(f"还原一致性检查通过率: {passed_count}/{total_chapters}")
    
    if passed_count == total_chapters:
        print("\n🎉 完美！算法逻辑在所有测试章节上均通过验证。")
    else:
        print("\n⚠️ 注意：存在还原不一致的情况，请检查特殊字符或换行符处理。")
