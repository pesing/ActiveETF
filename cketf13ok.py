import os
import re
from datetime import datetime, timedelta, timezone

import pandas as pd


ETF_LIST = [
    "00999A",
    "00981A",
    "00992A",
    "00982A",
]

SAVE_PATH = "data"
KEEP_DAYS = 4
TAIWAN_TZ = timezone(timedelta(hours=8))


def today_string():
    return datetime.now(TAIWAN_TZ).strftime("%Y-%m-%d")


def cleanup_old_csv(save_path, today_str):
    today = datetime.strptime(today_str, "%Y-%m-%d").date()
    date_pattern = re.compile(r"(\d{4}-\d{2}-\d{2})")

    print("\n清理舊 CSV...")

    for file_name in os.listdir(save_path):
        if not file_name.endswith(".csv") or file_name.startswith("latest_"):
            continue

        match = date_pattern.search(file_name)
        if not match:
            continue

        file_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
        if (today - file_date).days > KEEP_DAYS:
            file_path = os.path.join(save_path, file_name)
            os.remove(file_path)
            print(f"刪除：{file_name}")


def read_all_holdings(etf_code):
    try:
        return read_all_holdings_from_zdsetf(etf_code)
    except Exception as error:
        print(f"zdsetf 完整持股讀取失敗，改用 IFA：{error}")
        return read_all_holdings_from_ifa(etf_code)


def read_all_holdings_from_zdsetf(etf_code):
    url = f"https://zdsetf.com/etf/{etf_code}"
    tables = pd.read_html(url)

    for table in tables:
        columns = [str(column) for column in table.columns]
        required_columns = ["代號", "名稱", "股數", "權重(%)"]

        if set(required_columns).issubset(set(columns)):
            holding_df = table[required_columns].copy()
            holding_df = holding_df.rename(
                columns={
                    "代號": "股票代號",
                    "名稱": "股票名稱",
                    "股數": "持有股數",
                }
            )
            return normalize_holdings(holding_df)

    raise ValueError(f"{etf_code} 找不到 zdsetf 完整持股表")


def read_all_holdings_from_ifa(etf_code):
    url = f"https://info.ifa.ai/etf/{etf_code}"
    tables = pd.read_html(url)

    for table in tables:
        columns = [str(column) for column in table.columns]
        required_columns = ["股票代號", "股票名稱", "持股權重", "股數"]

        if set(required_columns).issubset(set(columns)):
            holding_df = table[required_columns].copy()
            holding_df = holding_df.rename(
                columns={
                    "持股權重": "權重(%)",
                    "股數": "持有股數",
                }
            )
            return normalize_holdings(holding_df)

    raise ValueError(f"{etf_code} 找不到完整持股表")


def read_same_day_compare_from_zdsetf(etf_code, today_df):
    url = f"https://zdsetf.com/etf/{etf_code}"
    tables = pd.read_html(url)
    compare_tables = []

    for table in tables:
        columns = [str(column) for column in table.columns]
        required_columns = ["代號", "名稱", "前日股數", "當日股數"]

        if set(required_columns).issubset(set(columns)):
            compare_tables.append(table[required_columns].copy())

    if not compare_tables:
        return build_compare(today_df, today_df)

    changed_df = pd.concat(compare_tables, ignore_index=True)
    changed_df = changed_df.rename(
        columns={
            "代號": "股票代號",
            "名稱": "股票名稱",
            "前日股數": "持有股數_昨日",
            "當日股數": "持有股數_今日",
        }
    )

    changed_df["股票代號"] = (
        changed_df["股票代號"]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
    )

    for column in ["持有股數_昨日", "持有股數_今日"]:
        changed_df[column] = normalize_number_series(changed_df[column]).astype(int)

    compare_df = today_df.rename(
        columns={
            "股票名稱": "股票名稱_今日",
            "權重(%)": "權重(%)_今日",
            "持有股數": "持有股數_今日",
        }
    )
    compare_df["股票名稱_昨日"] = compare_df["股票名稱_今日"]
    compare_df["持有股數_昨日"] = compare_df["持有股數_今日"]
    compare_df["權重(%)_昨日"] = compare_df["權重(%)_今日"]

    changed_detail_df = changed_df.copy()
    changed_df = changed_detail_df[["股票代號", "持有股數_昨日", "持有股數_今日"]]
    compare_df = pd.merge(
        compare_df.drop(columns=["持有股數_昨日"]),
        changed_df.rename(columns={"持有股數_今日": "異動後股數"}),
        on="股票代號",
        how="left",
    )

    compare_df["持有股數_昨日"] = compare_df["持有股數_昨日"].fillna(compare_df["持有股數_今日"])
    compare_df["持有股數_今日"] = compare_df["異動後股數"].fillna(compare_df["持有股數_今日"])
    compare_df = compare_df.drop(columns=["異動後股數"])
    compare_df["股票名稱"] = compare_df["股票名稱_今日"].combine_first(compare_df["股票名稱_昨日"])

    deleted_df = changed_detail_df[~changed_detail_df["股票代號"].isin(compare_df["股票代號"])].copy()
    if len(deleted_df) > 0:
        deleted_df["股票名稱_今日"] = deleted_df["股票名稱"]
        deleted_df["股票名稱_昨日"] = deleted_df["股票名稱"]
        deleted_df["權重(%)_今日"] = 0.0
        deleted_df["權重(%)_昨日"] = 0.0
        compare_df = pd.concat(
            [
                compare_df,
                deleted_df[
                    [
                        "股票代號",
                        "股票名稱_今日",
                        "權重(%)_今日",
                        "持有股數_今日",
                        "股票名稱_昨日",
                        "權重(%)_昨日",
                        "持有股數_昨日",
                        "股票名稱",
                    ]
                ],
            ],
            ignore_index=True,
        )

    compare_df["權重(%)_今日"] = pd.to_numeric(compare_df["權重(%)_今日"], errors="coerce").fillna(0)
    compare_df["權重(%)_昨日"] = pd.to_numeric(compare_df["權重(%)_昨日"], errors="coerce").fillna(0)
    compare_df["持有股數_今日"] = pd.to_numeric(compare_df["持有股數_今日"], errors="coerce").fillna(0).astype(int)
    compare_df["持有股數_昨日"] = pd.to_numeric(compare_df["持有股數_昨日"], errors="coerce").fillna(0).astype(int)
    compare_df["股數變化"] = compare_df["持有股數_今日"] - compare_df["持有股數_昨日"]
    compare_df["權重變化(%)"] = compare_df["權重(%)_今日"] - compare_df["權重(%)_昨日"]
    compare_df["變化"] = compare_df.apply(describe_change, axis=1)

    compare_df = compare_df[
        [
            "股票代號",
            "股票名稱",
            "持有股數_昨日",
            "持有股數_今日",
            "股數變化",
            "權重(%)_昨日",
            "權重(%)_今日",
            "權重變化(%)",
            "變化",
        ]
    ]

    compare_df["權重變化(%)"] = compare_df["權重變化(%)"].round(4)
    return compare_df.sort_values(
        ["變化", "權重(%)_今日"],
        ascending=[True, False],
    )


def normalize_holdings(holding_df):
    holding_df["股票代號"] = (
        holding_df["股票代號"]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
    )

    holding_df["股票名稱"] = holding_df["股票名稱"].astype(str).str.strip()

    holding_df["權重(%)"] = normalize_number_series(holding_df["權重(%)"])

    holding_df["持有股數"] = normalize_number_series(holding_df["持有股數"]).astype(int)

    holding_df = holding_df[holding_df["股票代號"].ne("")]
    holding_df = holding_df.sort_values("權重(%)", ascending=False).reset_index(drop=True)
    return holding_df[["股票代號", "股票名稱", "權重(%)", "持有股數"]]


def normalize_number_series(series):
    return pd.to_numeric(
        series.astype(str)
        .str.replace("%", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.replace("—", "0", regex=False)
        .str.strip(),
        errors="coerce",
    ).fillna(0)


def find_previous_all_csv(etf_code, today_str):
    files = sorted(
        file_name
        for file_name in os.listdir(SAVE_PATH)
        if file_name.startswith(f"{etf_code}_all_") and file_name.endswith(".csv")
    )

    for file_name in reversed(files):
        if today_str not in file_name:
            return os.path.join(SAVE_PATH, file_name)

    return None


def build_compare(today_df, previous_df):
    today_df = today_df.copy()
    previous_df = previous_df.copy()

    today_df["股票代號"] = today_df["股票代號"].astype(str)
    previous_df["股票代號"] = previous_df["股票代號"].astype(str)

    compare_df = pd.merge(
        today_df,
        previous_df,
        on="股票代號",
        how="outer",
        suffixes=("_今日", "_昨日"),
    )

    compare_df["股票名稱"] = compare_df["股票名稱_今日"].combine_first(compare_df["股票名稱_昨日"])

    for column in ["權重(%)_今日", "權重(%)_昨日", "持有股數_今日", "持有股數_昨日"]:
        compare_df[column] = pd.to_numeric(compare_df[column], errors="coerce").fillna(0)

    compare_df["股數變化"] = compare_df["持有股數_今日"] - compare_df["持有股數_昨日"]
    compare_df["權重變化(%)"] = compare_df["權重(%)_今日"] - compare_df["權重(%)_昨日"]

    compare_df["變化"] = compare_df.apply(describe_change, axis=1)

    compare_df = compare_df[
        [
            "股票代號",
            "股票名稱",
            "持有股數_昨日",
            "持有股數_今日",
            "股數變化",
            "權重(%)_昨日",
            "權重(%)_今日",
            "權重變化(%)",
            "變化",
        ]
    ]

    compare_df["持有股數_昨日"] = compare_df["持有股數_昨日"].astype(int)
    compare_df["持有股數_今日"] = compare_df["持有股數_今日"].astype(int)
    compare_df["股數變化"] = compare_df["股數變化"].astype(int)
    compare_df["權重變化(%)"] = compare_df["權重變化(%)"].round(4)

    return compare_df.sort_values(
        ["變化", "權重(%)_今日"],
        ascending=[True, False],
    )


def describe_change(row):
    if row["持有股數_昨日"] == 0 and row["持有股數_今日"] > 0:
        return "新增"
    if row["持有股數_昨日"] > 0 and row["持有股數_今日"] == 0:
        return "刪除"
    if row["股數變化"] > 0:
        return "增加"
    if row["股數變化"] < 0:
        return "減少"
    if row["權重變化(%)"] > 0:
        return "權重增加"
    if row["權重變化(%)"] < 0:
        return "權重減少"
    return "無變化"


def save_csv(df, path):
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"輸出：{path}")


def main():
    today_str = today_string()
    print(f"今天日期：{today_str}")

    os.makedirs(SAVE_PATH, exist_ok=True)
    cleanup_old_csv(SAVE_PATH, today_str)

    print("\ndata 目前檔案：")
    print(os.listdir(SAVE_PATH))

    for etf_code in ETF_LIST:
        print("\n======================")
        print(f"處理 {etf_code}")
        print("======================")

        try:
            today_df = read_all_holdings(etf_code)
            print(f"抓到完整持股：{len(today_df)} 筆")
            print(today_df.head(10))

            all_csv = os.path.join(SAVE_PATH, f"{etf_code}_all_{today_str}.csv")
            latest_all_csv = os.path.join(SAVE_PATH, f"latest_{etf_code}_all.csv")
            save_csv(today_df, all_csv)
            save_csv(today_df, latest_all_csv)

            previous_csv = find_previous_all_csv(etf_code, today_str)
            if previous_csv is None:
                print("找不到昨日完整持股 CSV，改用 zdsetf 今日前日差異表。")
                compare_df = read_same_day_compare_from_zdsetf(etf_code, today_df)
            else:
                print(f"比較基準：{previous_csv}")
                previous_df = pd.read_csv(previous_csv)
                compare_df = build_compare(today_df, previous_df)

            changed_count = len(compare_df[compare_df["變化"] != "無變化"])
            print(f"比較總筆數：{len(compare_df)}")
            print(f"異動筆數：{changed_count}")
            if len(compare_df) > 0:
                print(compare_df.head(20))

            compare_all_csv = os.path.join(SAVE_PATH, f"{etf_code}_compare_all_{today_str}.csv")
            latest_compare_all_csv = os.path.join(SAVE_PATH, f"latest_{etf_code}_compare_all.csv")
            save_csv(compare_df, compare_all_csv)
            save_csv(compare_df, latest_compare_all_csv)

        except Exception as error:
            print(f"{etf_code} 發生錯誤：{error}")

    print("\n全部完成")


if __name__ == "__main__":
    main()
