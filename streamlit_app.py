import streamlit as st
import pandas as pd
import plotly.express as px
import os

# 設定頁面語系與標題
st.set_page_config(page_title="勞資判決數據可視化", layout="wide")

st.title("⚖️ 勞資判決數據分析面板")
st.markdown("針對爬取到的職稱與薪資數據進行統計與可視化分析。")

CSV_FILE = "labor_judgments_final.csv"

if not os.path.exists(CSV_FILE):
    st.error(f"找不到數據檔案：{CSV_FILE}。請先執行 scraper.py 爬取數據。")
else:
    # 讀取數據
    df = pd.read_csv(CSV_FILE)
    
    # 數據清洗：確保薪資是數字，移除空值
    df['Monthly_Salary'] = pd.to_numeric(df['Monthly_Salary'], errors='coerce')
    df_clean = df.dropna(subset=['Monthly_Salary', 'Job_Title'])

    # 側邊欄統計
    st.sidebar.header("📊 數據概覽")
    st.sidebar.metric("總案件數", len(df))
    st.sidebar.metric("有效分析數", len(df_clean))
    st.sidebar.metric("平均月薪", f"NT$ {df_clean['Monthly_Salary'].mean():,.0f}")

    # 新增：高薪案件快速連結
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔝 高薪案件參考")
    top_cases = df_clean.sort_values(by='Monthly_Salary', ascending=False).head(5)
    for _, row in top_cases.iterrows():
        st.sidebar.markdown(f"**[{row['Job_Title']}]({row['URL']})**")
        st.sidebar.caption(f"月薪: NT$ {row['Monthly_Salary']:,.0f}")

    # 第一排：職稱分佈與薪資分佈
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📌 職稱出現頻率 (Top 10)")
        job_counts = df_clean['Job_Title'].value_counts().head(10).reset_index()
        job_counts.columns = ['Job_Title', 'Count']
        fig_job = px.bar(job_counts, x='Count', y='Job_Title', orientation='h', 
                         color='Count', color_continuous_scale='Viridis')
        st.plotly_chart(fig_job, use_container_width=True)

    with col2:
        st.subheader("💰 薪資分佈直方圖")
        fig_salary = px.histogram(df_clean, x="Monthly_Salary", nbins=20, 
                                  labels={'Monthly_Salary': '月薪 (TWD)'},
                                  color_discrete_sequence=['#636EFA'])
        st.plotly_chart(fig_salary, use_container_width=True)

    # 第二排：平均薪資分析
    st.subheader("📈 各職稱平均薪資分析")
    avg_salary = df_clean.groupby('Job_Title')['Monthly_Salary'].agg(['mean', 'count']).reset_index()
    avg_salary = avg_salary[avg_salary['count'] > 0].sort_values(by='mean', ascending=False).head(15)
    avg_salary.columns = ['職稱', '平均薪資', '樣本數']
    
    fig_avg = px.scatter(avg_salary, x="職稱", y="平均薪資", size="樣本數", color="平均薪資",
                         hover_name="職稱", size_max=60)
    st.plotly_chart(fig_avg, use_container_width=True)

    # 定義表格配置以減少重複代碼
    table_config = {
        "URL": st.column_config.LinkColumn("判決連結", display_text="🔗 查看判決主文"),
        "Monthly_Salary": st.column_config.NumberColumn("月薪", format="NT$ %d"),
        "Case_ID": "案件編號",
        "Job_Title": "職稱"
    }

    # 清洗後的數據表格
    with st.expander("🧹 查看清洗後的數據表格 (僅含有效薪資與職稱)"):
        st.dataframe(
            df_clean,
            column_config=table_config,
            hide_index=True,
            use_container_width=True
        )

    # 原始數據表格
    with st.expander("🔍 查看原始數據表格"):
        st.dataframe(
            df,
            column_config=table_config,
            hide_index=True,
            use_container_width=True
        )

    # 下載按鈕
    st.download_button(
        label="📥 下載清洗後的數據 (CSV)",
        data=df_clean.to_csv(index=False).encode('utf-8-sig'),
        file_name='cleaned_labor_data.csv',
        mime='text/csv',
    )

st.markdown("---")
st.caption("Powered by Gemini Code Assist | Data from Judicial Yuan")