from __future__ import annotations

import argparse
import os
from typing import cast

from xcrawler.storage.json_store import save_json

DEMO_USERNAME = "xcrawler_demo"


def _sample_data() -> dict[str, object]:
    raw = [
        {
            "id": "demo-3",
            "text": "Built a tiny local-first data tool today. Reproducible reports matter! #opensource",
            "created_at": "2026-07-10T12:30:00Z",
            "entities": {"hashtags": [{"tag": "opensource"}], "mentions": []},
        },
        {
            "id": "demo-2",
            "text": "Reading about trustworthy AI evaluation and evidence-driven product design.",
            "created_at": "2026-07-09T08:15:00Z",
            "entities": {"hashtags": [], "mentions": []},
        },
        {
            "id": "demo-1",
            "text": "A morning run, good coffee, then back to Python profiling. #python",
            "created_at": "2026-07-08T23:40:00Z",
            "entities": {"hashtags": [{"tag": "python"}], "mentions": []},
        },
    ]
    translated = [
        {
            "tweet_id": item["id"],
            "original": item["text"],
            "translated": translation,
            "detected_language": "en",
            "created_at": item["created_at"],
        }
        for item, translation in zip(
            raw,
            [
                "今天做了一个小型本地优先数据工具。可复现的报告很重要！",
                "正在阅读可信 AI 评估和证据驱动的产品设计。",
                "晨跑、好咖啡，然后继续做 Python 性能分析。",
            ],
        )
    ]
    profile = {
        "username": DEMO_USERNAME,
        "interests": [
            {
                "tag": "Open-source engineering",
                "level": "core",
                "confidence": 0.94,
                "evidence_status": "ok",
                "evidence_tweet_ids": ["demo-3", "demo-1"],
            },
            {
                "tag": "Trustworthy AI",
                "level": "core",
                "confidence": 0.86,
                "evidence_status": "ok",
                "evidence_tweet_ids": ["demo-2"],
            },
        ],
    }
    behavior = {"username": DEMO_USERNAME, "life_events": {}}
    return {"raw": raw, "translated": translated, "profile": profile, "behavior": behavior}


def generate_demo(output_dir: str) -> str:
    from visualize import generate_html_report

    os.makedirs(output_dir, exist_ok=True)
    data = _sample_data()
    save_json(os.path.join(output_dir, f"{DEMO_USERNAME}_raw_tweets.json"), data["raw"])
    save_json(os.path.join(output_dir, f"{DEMO_USERNAME}_translated.json"), data["translated"])
    save_json(os.path.join(output_dir, f"{DEMO_USERNAME}_interest_profile.json"), data["profile"])
    save_json(os.path.join(output_dir, f"{DEMO_USERNAME}_behavior.json"), data["behavior"])
    return cast(str, generate_html_report(DEMO_USERNAME, [], output_dir, data))


def main() -> int:
    parser = argparse.ArgumentParser(description="无需 API Key 的 xcrawler 示例报告")
    parser.add_argument("--output", default="demo_output", help="示例数据和报告输出目录")
    args = parser.parse_args()
    report_path = generate_demo(args.output)
    print(f"✅ Demo 已生成: {report_path}")
    print("🔒 使用内置虚构数据，未发起任何网络或 LLM 请求。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
