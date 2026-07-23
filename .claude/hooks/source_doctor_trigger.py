# UserPromptSubmit 훅 — 프롬프트가 "원인"/"원인해결"/"해결"로 시작하면
# source-doctor 스킬 호출 지시를 컨텍스트로 주입한다. (2026-07-23)
import json
import re
import sys

def main() -> None:
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 콘솔에서 한글·특수문자 출력 보장
        data = json.load(sys.stdin)
    except Exception:
        return
    prompt = (data.get("prompt") or "").strip()
    # 단어 경계: "해결해줘" 같은 일반 문장 오발동 방지 — 뒤가 공백/끝/구두점일 때만
    if re.match(r"^(원인해결|원인|해결)(\s|$|[:,.!?])", prompt):
        print(
            "[source-doctor 훅] 사용자가 트리거 단어(원인/원인해결/해결)로 시작하는 요청을 입력했다. "
            "Skill 도구로 'source-doctor' 스킬을 호출해 비활성(enabled:false) 소스의 "
            "원인·해결방안·예상토큰·기대효과를 진단하라. 트리거 단어 뒤에 소스명이 있으면 그 소스만 진단한다."
        )

if __name__ == "__main__":
    main()
