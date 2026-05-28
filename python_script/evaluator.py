import os
import re
import json
import statistics
from openai import OpenAI

# --- 配置路径常量 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POLICY_PATH = os.path.join(BASE_DIR, "cont_sample_7.md")        # 待评估的隐私政策文本
LIST_MD_PATH = os.path.join(BASE_DIR, "cont.md")         # 评分标准参考
CRITERIA_PATH = os.path.join(BASE_DIR, "cont.json")  # 评价结构与权重配置
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")      # API Key 配置文件
OUTPUT_PATH = os.path.join(BASE_DIR, "evaluation_result.json") # 输出结果文件
# -----------------------

def _load_key_from_config(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return None
    m = re.search(r"deepseek_api_key\s*:\s*[\"']?([^\"'\n]+)[\"']?", text)
    if m:
        return m.group(1).strip()
    return None

def build_prompt(policy_text, list_md_text, criteria):
    example = {"scores": {}, "special_flags": {}}
    
    for dim in criteria.get("dimensions", []):
        for sub in dim.get("sub_indicators", []):
            sub_id = sub["id"] if isinstance(sub, dict) else sub
            example["scores"][sub_id] = {"score": 0, "comment": "简短说明"}
            
    for penalty in criteria.get("penalties", {}).keys():
        example["special_flags"][penalty] = False

    instructions = (
        "请根据提供的隐私政策文本和评分标准（见下方参考内容），逐项对每个子指标给出分值和简短评语。\n"
        "输出必须为合法的 JSON，格式应与示例一致（示例在 example 字段），且仅输出 JSON 字符串，不包含额外解释文字。\n"
        "每个子指标 score 必须符合评分标准的要求，comment 为一段简短说明。\n"
        "在 special_flags 中返回布尔值指示是否出现对应的特殊扣分项（如采集某特定数据则为 true）。"
    )

    prompt = (
        "JSON 格式样例：\n" + json.dumps(example, ensure_ascii=False, indent=2) + "\n\n"
        + "评分标准（内容摘要）：\n" + list_md_text[:4000]
        + "\n\n隐私政策文本：\n" + policy_text[:40000]
        + "\n\n" + instructions
    )

    return prompt

def safe_parse_json(candidate):
    if isinstance(candidate, dict):
        return candidate
    text = candidate.strip()
    try:
        start = text.index("{")
        end = text.rindex("}")
        j = text[start:end+1]
        return json.loads(j)
    except Exception:
        return json.loads(text)

def compute_score(result_json, criteria):
    scores = result_json.get("scores", {})
    def s(key):
        try:
            return int(scores.get(key, {}).get("score", 0))
        except Exception:
            return 0

    dimension_scores = {}
    base_total = 0
    max_base_total = 0

    for dim in criteria.get("dimensions", []):
        dim_id = dim["id"]
        weight = dim.get("weight", 1.0)
        max_val = dim.get("max_score_per_item", 2)
        subs = dim.get("sub_indicators", [])
        
        raw_sum = sum(s(sub["id"] if isinstance(sub, dict) else sub) for sub in subs)
        weighted_score = raw_sum * weight
        max_weighted = len(subs) * max_val * weight
        
        dimension_scores[dim_id] = {
            "name": dim.get("name", dim_id),
            "score": weighted_score,
            "max": max_weighted
        }
        base_total += weighted_score
        max_base_total += max_weighted

    special = result_json.get("special_flags", {})
    deduction = 0
    penalties = criteria.get("penalties", {})
    
    for k, pen_info in penalties.items():
        if special.get(k, False):
            deduction += pen_info.get("deduction", 0)

    final_score = max(base_total - deduction, 0)
    pct = round(final_score / max_base_total * 100, 2) if max_base_total > 0 else 0
    return {
        "dimension_scores": dimension_scores,
        "base_total": base_total,
        "deduction": deduction,
        "final_score": final_score,
        "max_total": max_base_total,
        "percent": pct,
    }

def aggregate_results(results_list, criteria):
    aggregated = {"scores": {}, "special_flags": {}}

    sub_keys = []
    for dim in criteria.get("dimensions", []):
        sub_keys.extend(
            sub["id"] if isinstance(sub, dict) else sub
            for sub in dim.get("sub_indicators", [])
        )

    for k in sub_keys:
        vals = []
        comments = []
        for r in results_list:
            try:
                sc = int(r.get("scores", {}).get(k, {}).get("score", 0))
            except Exception:
                sc = 0
            vals.append(sc)
            c = r.get("scores", {}).get(k, {}).get("comment", "")
            comments.append(c)

        med = int(statistics.median(vals)) if vals else 0
        chosen_comment = ""
        for i, v in enumerate(vals):
            if v == med and comments[i]:
                chosen_comment = comments[i]
                break
        if not chosen_comment:
            for c in comments:
                if c:
                    chosen_comment = c
                    break

        aggregated["scores"][k] = {"score": med, "comment": chosen_comment}

    special_keys = list(criteria.get("penalties", {}).keys())
    for sk in special_keys:
        trues = sum(1 for r in results_list if r.get("special_flags", {}).get(sk, False))
        aggregated["special_flags"][sk] = (trues >= (len(results_list) / 2.0))

    return aggregated

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def evaluate_policy(text, mode, progress_callback=None, force=False, page_title="未知页面", page_url="未知URL"):
    if mode not in ["sec", "cont"]:
        raise ValueError("mode 必须是 'sec' 或 'cont'")

    list_md_path = os.path.join(BASE_DIR, f"{mode}.md")
    criteria_path = os.path.join(BASE_DIR, f"{mode}.json")
    output_path = os.path.join(BASE_DIR, f"{mode}_evaluation_result.json")

    with open(list_md_path, "r", encoding="utf-8") as f:
        list_md_text = f.read()
        
    criteria = load_json(criteria_path)

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        api_key = _load_key_from_config(CONFIG_PATH)
        if api_key:
            os.environ["DEEPSEEK_API_KEY"] = api_key

    if not api_key:
        raise RuntimeError("Deepseek API key 未找到。请设置环境变量或在 config.yaml 中添加。")
        
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    
    if mode == "sec":
        target_name = "隐私政策"
        other_name = "用户服务协议"
    else:
        target_name = "用户服务协议"
        other_name = "隐私政策"
    
    
    # 快速前置内容校验
    if not force:
        print(f"执行前置内容校验：是否包含 {target_name} 的特征...")
        if len(text.strip()) < 50:
             raise ValueError(f"网页内容过少，无法进行【{target_name}】的分析，请确保不要提取完全空洞或无加载内容。")
             
        check_prompt = f"请判定下方文本内容是否包含【{target_name}】的核心特征（或类似声明协议草案）。如果包含或大概率是一份协议条款内容，请仅回复唯一单词 YES；如果更像是【{other_name}】或者完全无关（如娱乐八卦、新闻报道、无文字商品页），请仅回复 NO。\n文本片段：\n{text[:3000]}"
        try:
            check_resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "你是一个严谨的网页分类器。只能输出 YES 或 NO。"},
                    {"role": "user", "content": check_prompt}
                ],
                temperature=0,
                max_tokens=10
            )
            ans = check_resp.choices[0].message.content.strip().upper()
            if "NO" in ans and "YES" not in ans:
                raise ValueError(f"[PRECHECK_FAILED] 当前网页未检测到【{target_name}】的显著特征。检测任务已跳过。\n请在正确的协议政策界面重试。")
        except ValueError as ve:
            raise ve
        except Exception as e:
            print(f"前置校验出现意外，防错强制放行后续深度分析进程：{e}")

    prompt = build_prompt(text, list_md_text, criteria)

    runs = []
    num_runs = 3
    for i in range(num_runs):
        print(f"开始第 {i+1} 次模型评估调用...")
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个根据给定评分细则对隐私政策逐项评分并输出严格符合示例 JSON 的评估助手。输出仅为 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )
        raw = None
        try:
            raw = response.choices[0].message.content
        except Exception:
            raw = getattr(response, "content", None)
        try:
            parsed = safe_parse_json(raw)
        except Exception as e:
            print(f"第 {i+1} 次返回内容无法解析为 JSON: {e}")
            parsed = {"scores": {}, "special_flags": {}}
        runs.append(parsed)
        
        if progress_callback:
            progress_callback(i + 1, num_runs)

    aggregated = aggregate_results(runs, criteria)
    computed = compute_score(aggregated, criteria)

    id_to_title = {}
    for dim in criteria.get("dimensions", []):
        for sub in dim.get("sub_indicators", []):
            if isinstance(sub, dict):
                id_to_title[sub["id"]] = sub.get("title", sub["id"])

    formatted_scores = []
    for dim in criteria.get("dimensions", []):
        dim_item = {
            "dimension": dim.get("name", dim["id"]),
            "items": []
        }
        for sub in dim.get("sub_indicators", []):
            sub_id = sub["id"] if isinstance(sub, dict) else sub
            v = aggregated.get("scores", {}).get(sub_id, {})
            # Remove numbering from the title
            title = id_to_title.get(sub_id, sub_id)
            title = re.sub(r'^\d+\.\d+\s*', '', title)
            dim_item["items"].append({
                "indicator": title,
                "score": v.get("score"),
                "max": dim.get("max_score_per_item", 2),
                "comment": v.get("comment", "")
            })
        if dim_item["items"]:
            formatted_scores.append(dim_item)

    special_items = []
    penalties_config = criteria.get("penalties", {})
    for k, val in aggregated.get("special_flags", {}).items():
        pen_info = penalties_config.get(k, {})
        desc = pen_info.get("desc", k)
        pen = pen_info.get("deduction", 0)
        special_items.append({"desc": desc, "hit": bool(val), "pen": pen})

    from datetime import datetime
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    text_length = len(text)
    text_length_k = round(text_length / 1000)

    out = {
        "page_title": page_title,
        "page_url": page_url,
        "evaluate_time": current_time,
        "text_length_k": text_length_k,
        "aggregated": aggregated, 
        "computed": computed,
        "formatted_scores": formatted_scores,
        "special_items": special_items
    }
    
    # 将本次结果追加到历史记录中
    history_data = []
    if os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                history_data = json.load(f)
                if getattr(history_data, 'items', None):
                    # 如果原先存的是字典，转化为列表
                    history_data = [history_data]
                elif not isinstance(history_data, list):
                    history_data = []
        except Exception:
            history_data = []
            
    history_data.append(out)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(history_data, f, ensure_ascii=False, indent=2)
        
    return out

def main():
    with open(POLICY_PATH, "r", encoding="utf-8") as f:
        policy_text = f.read()
        
    out = evaluate_policy(policy_text, mode="cont")
    aggregated = out["aggregated"]
    computed = out["computed"]
    
    criteria_path = os.path.join(BASE_DIR, "cont.json")
    criteria = load_json(criteria_path)

    print("各子指标（中位数结果）：")
    for k, v in aggregated.get("scores", {}).items():
        print(f"{k}: 分数={v.get('score')}，评语={v.get('comment')}")

    print("\n特殊扣分项：")
    penalties_config = criteria.get("penalties", {})

    for k, val in aggregated.get("special_flags", {}).items():
        pen_info = penalties_config.get(k, {})
        desc = pen_info.get("desc", k)
        pen = pen_info.get("deduction", 0)
        if val:
            print(f"- {desc}：扣分 {pen} 分")
        else:
            print(f"- {desc}：否")

    final_score = computed.get("final_score")
    max_total = computed.get("max_total")
    percent = computed.get("percent")
    print(f"\n最终总分: {final_score} / {max_total}，归一化得分: {percent}%")

if __name__ == "__main__":
    main()
