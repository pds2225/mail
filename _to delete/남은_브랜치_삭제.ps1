# mail 브랜치 청소 — 남은 삭제 대상 전부 (2026-07-23)
# 42개는 이미 삭제 완료. 아래는 이 세션에서 권한 차단으로 남았거나 추가 확인된 것.
# ★ 전부 "main에 이미 반영됨"을 내용 기준으로 검증 완료 → 삭제해도 코드 손실 0.
# 복구: 같은 폴더 "브랜치_SHA_복구백업_20260723.txt"에서 SHA 찾아
#       git branch <이름> <SHA> ; git push origin <이름>

cd D:\mail

# --- 1) 순서표 잔여 4개 (권한 차단으로 이 세션에서 못 지운 것) ---
git push origin --delete chore/remove-loan            # 이미 main 병합됨(loan 제거 완료)
git push origin --delete claude/bizinfo-collection-fix # 이미 main 병합됨
git push origin --delete chore/move-remaining-root-tests # #168이 이미 동일 작업 수행
git push origin --delete handoff/mobile               # POC 2개는 PR #169로 구출·병합 완료
# ※ handoff/mobile은 자동 스냅샷이 다시 만들 수 있음(오늘 10:53에도 자동 생성됨) — 다시 생겨도 무시 OK

# --- 2) 순서표에 없던 추가 브랜치 9개 (전부 main에 내용 반영 확인됨) ---
git push origin --delete claude/add-yesung-profile        # 0 ahead(완전 병합)
git push origin --delete claude/disable-auto-dev-schedule # 0 ahead — #167로 병합
git push origin --delete claude/hardening-integrated      # 0 ahead
git push origin --delete claude/hardening-part-a          # 0 ahead
git push origin --delete claude/hardening-part-b          # 0 ahead
git push origin --delete claude/repo-structure-cleanup    # 0 ahead
git push origin --delete claude/session-start-hook        # 0 ahead
git push origin --delete claude/local-concurrent-dev-git-pull-8g8xat # 예성 프로필 — main companies.json에 이미 존재
git push origin --delete feat/feedback-act                # 비공고 차단 — main monitor.py·테스트에 이미 존재(파일 동일)

# --- 3) 로컬 정리 (선택) ---
git worktree remove D:\mail\.claude\worktrees\rm-loan --force   # remove-loan 작업용 낡은 워크트리
git branch -D chore/remove-loan feat/recall-date feat/feedback-act feat/listonly-detail-enrich
# ※ feat/listonly-detail-enrich 로컬엔 미병합 커밋 2개(리스트온리 상세 재크롤)가 있으나
#   클라우드 분석에서 "이미 main에 더 나은 형태로 재구현됨" 판정된 계열 — 지우기 찜찜하면 이 줄만 빼세요.

# --- 4) 최종 확인 ---
git fetch --prune
git branch -r    # origin/main + origin/backup/WIN-K20QOC29TOB 만 남으면 성공
