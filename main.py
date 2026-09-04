import datetime
import altair as alt
import pandas as pd
import pytz
import requests
import streamlit as st

# -----------------------------------------------------------------------------
# Page Configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="어제 박스오피스",
    page_icon="🎬",
    layout="wide",
)


# -----------------------------------------------------------------------------
# Data Fetching Function (With Caching)
# -----------------------------------------------------------------------------
# ttl=3600: API 결과를 1시간(3600초) 동안 메모리에 기억하여 재요청을 방지합니다.
@st.cache_data(ttl=3600)
def fetch_box_office_data(api_key: str, target_date: str):
    """KOBIS API로부터 지정된 날짜의 박스오피스 데이터를 가져오는 함수"""
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {"key": api_key, "targetDt": target_date}

    try:
        response = requests.get(url, params=params, timeout=10)
        # 네트워크 응답 자체가 실패했을 경우 에러 처리
        if response.status_code != 200:
            return None, f"서버 응답 오류 (상태 코드: {response.status_code})"

        data = response.json()

        # KOBIS API는 키가 잘못되어도 200 OK를 반환하고 faultInfo 객체를 넘겨줍니다.
        if "faultInfo" in data:
            message = data["faultInfo"].get(
                "message", "인증키 문제로 오류가 발생했습니다."
            )
            return None, f"API 오류 안내: {message}"

        # 정상 응답 내 박스오피스 결과 확인
        box_office_result = data.get("boxOfficeResult", {})
        daily_list = box_office_result.get("dailyBoxOfficeList", [])

        if not daily_list:
            return None, "해당 날짜의 데이터가 비어 있습니다."

        return daily_list, None

    except requests.exceptions.RequestException as e:
        return None, f"통신 문제 발생: {str(e)}"


# -----------------------------------------------------------------------------
# Main Application
# -----------------------------------------------------------------------------
def main():
    st.title("🎬 어제 일별 박스오피스")

    # 1. API 키 확인 (st.secrets)
    if "KOBIS_KEY" not in st.secrets:
        st.error("🚨 API 인증키(KOBIS_KEY)를 찾을 수 없습니다.")
        st.info(
            """
            **확인해 주세요:**
            1. Streamlit Cloud 배포 화면의 **Secrets** 설정 영역에 `KOBIS_KEY = "발급받은 키"`를 입력했는지 확인하세요.
            2. 로컬 실행 시에는 `.streamlit/secrets.toml` 파일 안에 키가 올바르게 입력되어 있는지 확인하세요.
            """
        )
        return

    api_key = st.secrets["KOBIS_KEY"]

    # 2. 한국 시간(KST) 기준 '어제' 날짜 계산
    kst = pytz.timezone("Asia/Seoul")
    now_kst = datetime.datetime.now(kst)
    yesterday_kst = now_kst - datetime.timedelta(days=1)
    target_date_str = yesterday_kst.strftime("%Y%m%d")
    formatted_date_display = yesterday_kst.strftime("%Y년 %m월 %d일")

    st.caption(f"📅 기준 날짜: **{formatted_date_display}** (한국 시간 기준)")

    # 3. 데이터 가져오기
    daily_list, error_message = fetch_box_office_data(api_key, target_date_str)

    # 4. 에러 발생 시 안내 화면 출력
    if error_message or not daily_list:
        st.error("데이터를 가져오는 중 문제가 발생했습니다.")
        st.warning(f"**상세 내용:** {error_message}")
        st.info(
            """
            **점검 목록:**
            - 영화진흥위원회(KOBIS) 개발자 센터에서 발급받은 **KOBIS_KEY**가 정확한지 확인해 주세요.
            - 일일 호출 수 한도를 초과하지 않았는지 점검하세요.
            - KOBIS 서버 점검 중일 수 있으니 잠시 후 다시 시도해 보세요.
            """
        )
        return

    # 5. 데이터 가공 (문자열 -> 숫자 변환)
    df = pd.DataFrame(daily_list)

    # 문자열 타입인 숫자를 수치 데이터형으로 변환
    numeric_columns = ["rank", "audiCnt", "audiAcc", "scrnCnt"]
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 순위 기준 오름차순 정렬
    df = df.sort_values("rank").reset_index(drop=True)

    # 6. 1위 영화 지표 카드 (st.metric) 출력
    top_1 = df.iloc[0]
    st.markdown("### 🏆 어제 1위 영화")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="영화명", value=top_1["movieNm"])
    with col2:
        st.metric(
            label="어제 관객수", value=f"{top_1['audiCnt']:,} 명"
        )  # 천 단위 쉼표 표기
    with col3:
        st.metric(label="누적 관객수", value=f"{top_1['audiAcc']:,} 명")

    st.divider()

    # 7. 관객수 상위 5편 막대그래프 (Altair 사용)
    st.markdown("### 📊 관객수 상위 5개 영화")
    top_5_df = df.head(5)

    chart = (
        alt.Chart(top_5_df)
        .mark_bar()
        .encode(
            x=alt.X(
                "movieNm:N",
                sort=alt.EncodingSortField(field="rank", order="ascending"),
                title="영화명",
            ),
            y=alt.Y("audiCnt:Q", title="관객수 (명)"),
            color=alt.Color("movieNm:N", legend=None),
            tooltip=[
                alt.Tooltip("movieNm", title="영화명"),
                alt.Tooltip("rank", title="순위"),
                alt.Tooltip("audiCnt", title="어제 관객수", format=","),
            ],
        )
        .properties(height=350)
    )

    st.altair_chart(chart, use_container_width=True)

    st.divider()

    # 8. 전체 박스오피스 데이터 표 출력
    st.markdown("### 📋 전체 박스오피스 순위")

    display_df = df[
        ["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]
    ].copy()
    display_df.columns = [
        "순위",
        "영화명",
        "개봉일",
        "관객수",
        "누적관객",
        "스크린수",
    ]

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "관객수": st.column_config.NumberColumn(format="%d 명"),
            "누적관객": st.column_config.NumberColumn(format="%d 명"),
            "스크린수": st.column_config.NumberColumn(format="%d 개"),
        },
    )


if __name__ == "__main__":
    main()
