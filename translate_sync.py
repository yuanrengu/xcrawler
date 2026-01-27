import os
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from dotenv import load_dotenv

# Reuse logic from main.py
# Make sure main.py is in the same directory or PYTHONPATH
from main import (
    deepseek_translate, 
    detect_language, 
    clean_text, 
    load_translation_cache, 
    save_translation_cache,
    MAX_WORKERS,
    CACHE_DIR
)

load_dotenv()

TARGET_USERNAME = os.getenv("TARGET_USERNAME", "MiracleHe")

def load_data(username):
    """Load raw and translated data"""
    raw_file = os.path.join(CACHE_DIR, f"{username}_raw_tweets.json")
    translated_file = os.path.join(CACHE_DIR, f"{username}_translated.json")
    
    raw_tweets = []
    if os.path.exists(raw_file):
        with open(raw_file, 'r', encoding='utf-8') as f:
            raw_tweets = json.load(f)
            
    translated_data = []
    if os.path.exists(translated_file):
        with open(translated_file, 'r', encoding='utf-8') as f:
            translated_data = json.load(f)
            
    return raw_tweets, translated_data, translated_file

import argparse

def main():
    parser = argparse.ArgumentParser(description="翻译同步/重翻工具")
    parser.add_argument("--force", action="store_true", help="强制重新翻译所有推文（忽略缓存和现有翻译）")
    args = parser.parse_args()

    print("=" * 60)
    print(f"🔄 翻译同步工具 (Translation Sync)")
    print(f"🎯 目标用户: {TARGET_USERNAME}")
    if args.force:
        print("⚠️  模式: 强制重新翻译 (Force Re-translation)")
    print("=" * 60 + "\n")

    # 1. Load data
    print("📂 加载数据...")
    raw_tweets, translated_data, translated_file_path = load_data(TARGET_USERNAME)
    print(f"   原始推文: {len(raw_tweets)} 条")
    print(f"   已翻译推文: {len(translated_data)} 条")

    # Load translation cache
    import main
    if args.force:
        print("🧹 强制模式：忽略并清除内存中的翻译缓存")
        main.translation_cache = {}
        # We don't delete the file on disk yet, just don't use it in memory
    else:
        translation_cache = load_translation_cache()
        main.translation_cache = translation_cache
        print(f"   翻译缓存: {len(translation_cache)} 条\n")

    # 2. Identify tweets to process
    print("🔍 检查待翻译推文...")
    
    to_process = []
    
    if args.force:
        # Process ALL raw tweets
        translated_texts = set() # Empty set so everything is "new"
    else:
        translated_texts = set(item["original"] for item in translated_data)
    
    for t in raw_tweets:
        text = t.get("text", "")
        clean = clean_text(text)
        
        if len(clean) < 6:
            continue
            
        if args.force or clean not in translated_texts:
            detected_lang = detect_language(clean)
            to_process.append({
                "original": clean,
                "lang": detected_lang,
                "created_at": t.get("created_at", "")
            })

    if not to_process:
        print("🎉 所有推文都已翻译，无需更新！")
        return

    print(f"📝 发现 {len(to_process)} 条推文需要翻译")
    
    # 3. Translate
    print(f"🚀 启动 {MAX_WORKERS} 个线程进行翻译...")
    
    # If forcing, we might want to reset the translated_data list or overwrite updates.
    # The safest way for "re-translate all" is to assume new_translations WILL BE the full list 
    # (minus maybe short ones we skipped)
    # BUT `to_process` loops over raw_tweets. So if we successfully translate everything in `to_process`, 
    # we effectively have the full dataset.
    
    if args.force:
        # Reset translated_data to empty if we are effectively re-doing everything?
        # Or we can just append and then dedupe at the end? 
        # If we re-translate, we will have duplicates if we extend `translated_data`.
        # So we should probably start fresh.
        print("⚠️  强制模式：将覆盖现有的翻译文件")
        translated_data = [] 

    new_translations = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Pass use_cache=False if force is on
        use_cache_flag = not args.force
        
        future_to_item = {
            executor.submit(deepseek_translate, item["original"], item["lang"], use_cache=use_cache_flag): item
            for item in to_process
        }
        
        try:
            count = 0
            for future in tqdm(as_completed(future_to_item), total=len(to_process), desc="翻译进度"):
                item = future_to_item[future]
                try:
                    translated_text = future.result()
                    if translated_text:
                        new_item = {
                            "original": item["original"],
                            "translated": translated_text,
                            "detected_language": item["lang"],
                            "created_at": item["created_at"]
                        }
                        new_translations.append(new_item)
                        count += 1
                        
                        # Incremental save every 5 items
                        if count % 5 == 0:
                             # Merge: if force, new_translations IS the data. If sync, translated_data + new.
                             current_data = translated_data + new_translations
                             current_data.sort(key=lambda x: x.get("created_at", ""), reverse=True)
                             with open(translated_file_path, 'w', encoding='utf-8') as f:
                                json.dump(current_data, f, ensure_ascii=False, indent=2)
                             
                             # Save cache (update with new translations)
                             if not args.force:
                                 # Only update cache file if we are using it? 
                                 # actually even if force, we might want to populate cache for NEXT time.
                                 # But if we force, we want to overwrite cache entries?
                                 # deepseek_translate updates in-memory cache automatically.
                                 pass
                             
                             save_translation_cache(main.translation_cache)
                             
                except Exception as e:
                    print(f"❌ 翻译出错: {str(e)}")
        except KeyboardInterrupt:
            print("\n🛑 用户手动中断同步，正在保存已完成的翻译...")

    if new_translations:
        # Final save
        current_data = translated_data + new_translations
        current_data.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        print(f"\n💾 保存更新后的翻译数据 ({len(current_data)} 条)...")
        with open(translated_file_path, 'w', encoding='utf-8') as f:
            json.dump(current_data, f, ensure_ascii=False, indent=2)
            
        # Save cache
        save_translation_cache(main.translation_cache)
        
        if args.force:
             print(f"✅ 重新翻译完成！共处理 {len(new_translations)} 条")
        else:
             print(f"✅ 同步完成！新增翻译 {len(new_translations)} 条")
    else:
        print("\n⚠️ 未能生成有效翻译")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
