import os
import re

def remove_overlap_from_start(prev_text, current_text, search_window=50):
    """
    检查 current_text 的开头是否重复了 prev_text 的结尾。
    如果有，去除重复部分。
    
    Args:
        prev_text: 之前已合并的文本
        current_text: 当前要合并的文本
        search_window: 向前/后搜索的最大字符数（为了性能，不全文搜索）
    """
    if not prev_text or not current_text:
        return current_text

    # 简单清洗用于比较（去除首尾空白），但保留原始内容用于切片
    # 这里我们直接比对原始字符串的边界，因为 strip 可能会破坏结构
    
    # 确定最大可能的重叠长度
    max_len = min(len(prev_text), len(current_text), search_window)
    
    # 从最大长度开始尝试匹配，贪婪匹配最长重叠
    # 例如：prev="...ABC", curr="ABC..." -> 匹配长度3
    for k in range(max_len, 0, -1):
        suffix = prev_text[-k:]
        prefix = current_text[:k]
        
        # 如果重叠部分完全匹配
        if suffix == prefix:
            # 这是一个重叠！返回去除前缀后的 current_text
            # print(f"  [Merge Info] 检测到重叠 {k} 字符: '{suffix}'")
            return current_text[k:]
            
    return current_text

def merge_chunks_to_chapter(chunk_outputs, output_dir, chapter_title=""):
    """
    Args:
        chunk_outputs (list[dict]): 包含翻译结果的字典列表。每个字典结构如下:
            {
                "chunk_id": str,       
                "chapter_id": 1,
                "back_zh_to_en": str,  
                "meta": dict,          
                ...                    
            }
        output_dir (str): 生成文件的存储目录路径 (e.g., "data/output")。
        chapter_title (str, optional): 章节标题。若提供，将以 Markdown H1 (# Title) 格式写入文件首行。

    Returns:
        str: 生成文件的完整路径 (filepath)，例如 "data/output/chapter_1_en.txt"。
        None: 如果输入列表 chunk_outputs 为空。
    """
    if not chunk_outputs:
        print("⚠️ Warning: 没有可合并的 Chunk 数据")
        return None

    # 1. 排序 (按 chunk_id 字符串顺序: 1-001, 1-002...)
    sorted_outputs = sorted(chunk_outputs, key=lambda x: x['chunk_id'])
    
    merged_parts = []
    
    # 2. 处理标题
    if chapter_title:
        # Markdown 格式标题
        merged_parts.append(f"# {chapter_title}")
    
    # 用于追踪上一段的文本（未清洗换行符的），用于重叠检测
    last_part_raw = "" 

    # 3. 循环处理
    for item in sorted_outputs:
        # 获取译文 (英文)
        raw_text = item.get('back_zh_to_en', '')
        
        if not raw_text:
            continue

        # 如果这不是第一段，且上一段有内容，检查边界
        cleaned_text = raw_text
        if last_part_raw:
            # 去除当前段开头与上一段结尾重复的部分
            prev_tail_stripped = last_part_raw.rstrip()
            curr_head_stripped = raw_text.lstrip()
            
            
            # 核心去重
            text_no_overlap = remove_overlap_from_start(prev_tail_stripped, curr_head_stripped)
            
            # 如果发生了裁剪
            if len(text_no_overlap) < len(curr_head_stripped):
                # 说明检测到了重叠，采纳去重后的文本
                cleaned_text = text_no_overlap
            else:
                # 没重叠，保留原文本（包含左侧可能的缩进，或者我们统一 strip）
                # 这里建议统一 strip，由合并器控制段间距
                cleaned_text = raw_text.strip()
        else:
            cleaned_text = raw_text.strip()

        # 去除可能残留的奇怪符号或多余空行
        cleaned_text = cleaned_text.strip()
        
        if cleaned_text:
            merged_parts.append(cleaned_text)
            # 更新 last_part_raw，用于下一次比较
            last_part_raw = cleaned_text

    # 4. 拼接
    # 使用 "\n\n" 确保段落之间有清晰的空行
    full_text = "\n\n".join(merged_parts)
    
    # 5. 确定输出文件名
    first_chunk = sorted_outputs[0]
    chapter_id = "unknown"
    
    # 获取 Chapter ID 逻辑
    if 'chapter_id' in first_chunk:
        chapter_id = first_chunk['chapter_id']
    elif 'meta' in first_chunk and 'chapter_id' in first_chunk['meta']:
        chapter_id = first_chunk['meta']['chapter_id']
    else:
        try:
            chapter_id = first_chunk['chunk_id'].split('-')[0]
        except:
            pass

    filename = f"chapter_{chapter_id}_en.txt"
    filepath = os.path.join(output_dir, filename)
    
    os.makedirs(output_dir, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(full_text)
        
    print(f"✅ Merged {len(sorted_outputs)} chunks into {filepath}")
    return filepath


def merge_chapters_to_book(chapter_dir, output_path="book_merged_en.txt"):
    """
    将目录下的所有章节文件合并成一本完整的书。
    
    Args:
        chapter_dir (str): 存放章节 txt 文件的目录路径。
        output_path (str): 输出的完整书本文件路径。
        
    Returns:
        str: 输出文件的路径。
    """
    if not os.path.exists(chapter_dir):
        print(f"❌ Error: 目录不存在 {chapter_dir}")
        return None

    # 1. 查找文件
    # 假设文件名格式为 "chapter_1_en.txt"
    all_files = os.listdir(chapter_dir)
    chapter_files = [f for f in all_files if f.startswith("chapter_") and f.endswith("_en.txt")]
    
    if not chapter_files:
        print("⚠️ Warning: 在目录中没有找到章节文件 (chapter_*_en.txt)")
        return None

    # 2. 自然排序 (Natural Sort)
    # 我们需要从文件名提取数字ID进行排序，否则 '10' 会排在 '2' 前面
    def extract_chapter_number(filename):
        # 使用正则提取 "chapter_" 和 "_en" 之间的数字
        match = re.search(r'chapter_(\d+)_', filename)
        if match:
            return int(match.group(1))
        return float('inf') # 如果没找到数字，扔到最后面

    sorted_files = sorted(chapter_files, key=extract_chapter_number)
    
    print(f"📚 发现 {len(sorted_files)} 个章节，准备合并...")
    print(f"   排序预览: {sorted_files[:3]} ... {sorted_files[-1:]}")

    # 3. 读取并拼接
    book_content = []
    
    for filename in sorted_files:
        filepath = os.path.join(chapter_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    book_content.append(content)
        except Exception as e:
            print(f"❌ 读取文件 {filename} 失败: {e}")

    # 4. 写入整书
    # 使用 3 个换行符分隔不同章节，视觉上更清晰
    separator = "\n\n" + "="*10 + "\n\n" 
    full_text = separator.join(book_content)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_text)
        
    print(f"🎉 全书合并完成！已保存至: {output_path} (总长度: {len(full_text)} 字符)")
    return output_path

# ==========================================
# 测试代码：测试重叠和空行处理
# ==========================================
if __name__ == "__main__":
    import shutil
    
    print("🚀 测试：Merge 模块 (重叠处理 & 格式清洗)")
    
    # 构造测试数据：包含重叠、多余空行、乱序
    mock_data = [
        {
            "chunk_id": "1-001",
            "back_zh_to_en": "  This is paragraph two. \n\n", # 多余空行
            "chunk_note": "正常段落"
        },
        {
            "chunk_id": "1-000",
            "back_zh_to_en": "This is paragraph one. It ends here.",
            "chunk_note": "第一段"
        },
        {
            "chunk_id": "1-002", 
            "back_zh_to_en": "paragraph two. This is paragraph three.", # 【重叠测试】开头重复了上一段的结尾
            "chunk_note": "包含重叠的段落"
        },
        {
            "chunk_id": "1-003",
            "back_zh_to_en": "This is paragraph three. The End.", # 【重叠测试】完全重复了上一段的结尾
            "chunk_note": "包含重叠"
        }
    ]

    test_dir = "data/test_merge_overlap"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)

    output_path = merge_chunks_to_chapter(mock_data, test_dir, chapter_title="Overlap Test")
    
    if output_path and os.path.exists(output_path):
        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()
            print("\n📄 --- 合并结果预览 ---")
            print(content)
            print("-----------------------")
            
            # 验证点 1: 顺序是否正确 (1-000 在前)
            assert content.find("paragraph one") < content.find("paragraph three")
            
            # 验证点 2: 重叠是否去除
            # 原始数据 1-001 结尾是 "paragraph two."
            # 原始数据 1-002 开头是 "paragraph two. This is..."
            # 合并后不应该出现 "paragraph two. paragraph two."
            if "paragraph two. paragraph two." not in content:
                print("✅ 重叠去除成功！")
            else:
                print("❌ 失败：发现了未去除的重叠文本。")

            # 验证点 3: 空行清洗
            # 1-001 原文有很多 \n\n，合并后应该被 normalize 为标准的 \n\n
            if "\n\n\n" not in content:
                print("✅ 空行清洗成功！")