# ============================================
# 主動ETF 前10大持股 CSV 產生器 + 昨日比較版
# GitHub Actions 版
# ============================================

import os
import pandas as pd
from datetime import datetime

# ============================================
# ETF清單
# ============================================

ETF_LIST = [
    "00999A",
    "00981A",
    "00992A",
    "00982A"
]

# ============================================
# 今日日期
# ============================================

today_str = datetime.today().strftime("%Y-%m-%d")

# ============================================
# GitHub Pages data 資料夾
# ============================================

SAVE_PATH = "data"

os.makedirs(
    SAVE_PATH,
    exist_ok=True
)

# ============================================
# 逐一抓ETF
# ============================================

for ETF_CODE in ETF_LIST:

    print("\n======================")
    print(f"抓取 {ETF_CODE}")
    print("======================")

    URL = (
        "https://www.moneydj.com/ETF/X/Basic/"
        f"Basic0007.xdjhtm?etfid={ETF_CODE.lower()}.tw"
    )

    print(URL)

    try:

        # ====================================
        # 抓 tables
        # ====================================

        tables = pd.read_html(URL)

        print(f"找到 {len(tables)} 個 tables")

        # ====================================
        # 自動找持股表
        # ====================================

        holding_df = None

        for i, table in enumerate(tables):

            cols = [str(c) for c in table.columns]

            if any(
                "個股名稱" in c
                for c in cols
            ):

                holding_df = table

                print(f"找到持股表 TABLE {i}")

                break

        # ====================================
        # 找不到持股表
        # ====================================

        if holding_df is None:

            print("找不到持股表")

            continue

        # ====================================
        # 第一欄
        # ====================================

        first_col = holding_df.columns[0]

        # ====================================
        # 拆股票名稱與代號
        # ====================================

        holding_df["股票名稱"] = (
            holding_df[first_col]
            .astype(str)
            .str.extract(r"(.+)\(")
        )

        holding_df["股票代號"] = (
            holding_df[first_col]
            .astype(str)
            .str.extract(r"\((\d+)")
        )

        # ====================================
        # 找投資比例欄位
        # ====================================

        ratio_col = None

        for col in holding_df.columns:

            if "投資比例" in str(col):

                ratio_col = col
                break

        # ====================================
        # 找持有股數欄位
        # ====================================

        share_col = None

        for col in holding_df.columns:

            if "持有股數" in str(col):

                share_col = col
                break

        # ====================================
        # 整理欄位
        # ====================================

        keep_cols = [
            "股票代號",
            "股票名稱"
        ]

        if ratio_col:

            keep_cols.append(ratio_col)

        if share_col:

            keep_cols.append(share_col)

        result_df = holding_df[
            keep_cols
        ]

        # ====================================
        # 前10大
        # ====================================

        top10_df = result_df.head(10)

        # ====================================
        # 今日CSV
        # ====================================

        csv_file = (
            f"{SAVE_PATH}/"
            f"{ETF_CODE}_top10_"
            f"{today_str}.csv"
        )

        top10_df.to_csv(

            csv_file,

            index=False,

            encoding="utf-8-sig"
        )

        print(f"輸出：{csv_file}")

        # ====================================
        # 找歷史CSV
        # ====================================

        files = sorted([

            f for f in os.listdir(SAVE_PATH)

            if (
                f.startswith(
                    f"{ETF_CODE}_top10_"
                )
                and
                f.endswith(".csv")
            )
        ])

        # ====================================
        # 至少兩天資料
        # ====================================

        if len(files) >= 2:

            yesterday_csv = (
                f"{SAVE_PATH}/{files[-2]}"
            )

            print(f"比較昨日：{yesterday_csv}")

            # ====================================
            # 讀昨日CSV
            # ====================================

            yesterday_df = pd.read_csv(
                yesterday_csv
            )

            # ====================================
            # 股票代號統一字串
            # ====================================

            top10_df["股票代號"] = (
                top10_df["股票代號"]
                .astype(str)
            )

            yesterday_df["股票代號"] = (
                yesterday_df["股票代號"]
                .astype(str)
            )

            # ====================================
            # merge
            # ====================================

            compare_df = pd.merge(

                top10_df,
                yesterday_df,

                on="股票代號",

                how="outer",

                suffixes=(
                    "_今日",
                    "_昨日"
                )
            )

            # ====================================
            # 空值補0
            # ====================================

            compare_df = compare_df.fillna(0)

            # ====================================
            # 持有股數轉數字
            # ====================================

            compare_df["持有股數_今日"] = pd.to_numeric(

                compare_df["持有股數_今日"],

                errors="coerce"

            ).fillna(0)

            compare_df["持有股數_昨日"] = pd.to_numeric(

                compare_df["持有股數_昨日"],

                errors="coerce"

            ).fillna(0)

            # ====================================
            # 股數變化
            # ====================================

            compare_df["股數變化"] = (

                compare_df["持有股數_今日"]
                -
                compare_df["持有股數_昨日"]
            )

            # ====================================
            # 判斷加減碼
            # ====================================

            compare_df["變化"] = compare_df[
                "股數變化"
            ].apply(

                lambda x:
                    "加碼" if x > 0 else
                    "減碼" if x < 0 else
                    "不變"
            )

            # ====================================
            # 只保留變化
            # ====================================

            change_df = compare_df[
                compare_df["股數變化"] != 0
            ]

            # ====================================
            # compare CSV
            # 即使沒變化也輸出
            # ====================================

            compare_csv = (
                f"{SAVE_PATH}/"
                f"{ETF_CODE}_compare_"
                f"{today_str}.csv"
            )

            change_df.to_csv(

                compare_csv,

                index=False,

                encoding="utf-8-sig"
            )

            print(f"輸出：{compare_csv}")

            # ====================================
            # latest compare CSV
            # ====================================

            latest_csv = (
                f"{SAVE_PATH}/"
                f"latest_{ETF_CODE}_compare.csv"
            )

            change_df.to_csv(

                latest_csv,

                index=False,

                encoding="utf-8-sig"
            )

            print(f"更新：{latest_csv}")

            # ====================================
            # 顯示結果
            # ====================================

            if len(change_df) == 0:

                print("今日無變化")

            else:

                print("今日有持股變化")

        else:

            print("沒有昨日CSV")

    except Exception as e:

        print("發生錯誤：")

        print(e)

print("\n全部完成")