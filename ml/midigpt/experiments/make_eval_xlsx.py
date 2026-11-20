"""eval_results.csv → 악기별 시트 + 요약 엑셀.  사용법: python scripts/make_eval_xlsx.py [eval_results.csv] [출력.xlsx]"""
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter as L
import sys
CSV=sys.argv[1] if len(sys.argv)>1 else 'results/eval_results.csv'
OUT=sys.argv[2] if len(sys.argv)>2 else 'results/MIDI-GPT_생성평가_곡별.xlsx'
d=pd.read_csv(CSV)
F=lambda **k: Font(name='Arial', **k)
HF=PatternFill('solid',fgColor='1F3A5F'); AF=PatternFill('solid',fgColor='E8EEF5'); NF=PatternFill('solid',fgColor='F3F3F3')
thin=Side(style='thin',color='BFBFBF'); B=Border(top=thin,bottom=thin,left=thin,right=thin)
MEL=[('CP ↑','cp'),('CP활성 ↑','cp_active'),('PCHE차이 ↓','pche_diff'),('PCH유사 ↑','pch_sim'),('GS차이 ↓','gs_diff'),('GS일치 ↑','gs_match')]
DRM=[('GS차이 ↓','gs_diff'),('GS일치 ↑','gs_match'),('F1','f1')]
TAIL=[('마디당 음 (원)','notes_per_bar_orig','0.0'),('마디당 음 (생)','notes_per_bar_gen','0.0'),('빈 마디 (원)','empty_bars_orig','0'),('빈 마디 (생)','empty_bars_gen','0')]
MISS={('bass','Track00017'):'원곡에 베이스 없음 (비교 불가)',('drums','Track00008'):'생성 실패 (재시도 필요)'}
wb=Workbook(); wb.remove(wb.active)
insts=[('piano','피아노'),('guitar','기타'),('bass','베이스'),('drums','드럼')]
avg_ref={}
for inst,ko in insts:
    ws=wb.create_sheet(ko); s=d[d.instrument==inst].set_index('song')
    cols=[(h,c,'0.00') for h,c in (DRM if inst=='drums' else MEL)]+TAIL
    ws.append(['곡']+[h for h,_,_ in cols])
    for c in ws[1]: c.font=F(bold=True,color='FFFFFF'); c.fill=HF; c.alignment=Alignment(horizontal='center',vertical='center',wrap_text=True); c.border=B
    for i in range(1,21):
        t=f'Track{i:05d}'; r=i+1
        ws.cell(r,1,t)
        if t in s.index:
            for j,(h,c,fmt) in enumerate(cols,2):
                v=s.loc[t,c]; cell=ws.cell(r,j,None if pd.isna(v) else float(v)); cell.number_format=fmt
        else:
            ws.cell(r,2,MISS.get((inst,t),'데이터 없음')); ws.merge_cells(start_row=r,start_column=2,end_row=r,end_column=len(cols)+1)
            for j in range(1,len(cols)+2): ws.cell(r,j).fill=NF
            ws.cell(r,2).font=F(italic=True,color='7F7F7F')
    ar=22; ws.cell(ar,1,'평균')
    for j,(h,c,fmt) in enumerate(cols,2):
        cl=L(j); x=ws.cell(ar,j,f'=AVERAGE({cl}2:{cl}21)'); x.number_format=fmt
        avg_ref[(ko,h)]=f"='{ko}'!{cl}{ar}"
    for row in ws.iter_rows(min_row=2,max_row=ar):
        for c in row:
            c.border=B
            if c.font.color is None or c.font.color.rgb in (None,'FF000000'): c.font=F(bold=(c.row==ar))
            if c.column>1: c.alignment=Alignment(horizontal='center')
    for c in ws[ar]: c.fill=AF; c.font=F(bold=True)
    ws.column_dimensions['A'].width=13
    for j in range(2,len(cols)+2): ws.column_dimensions[L(j)].width=12
    ws.row_dimensions[1].height=32; ws.freeze_panes='B2'
    ws.cell(24,1,'↑ 높을수록, ↓ 낮을수록 원곡에 가까움. (원)=원래 파트, (생)=MIDI-GPT 생성 파트. 출처: eval_results.csv (eval_generation.py, yellow_medium, BabySlakh 20곡)').font=F(italic=True,size=9,color='595959')
# summary
ws=wb.create_sheet('요약',0)
ws['A1']='MIDI-GPT 생성 평가 — 악기별 평균 (BabySlakh 20곡)'; ws['A1'].font=F(bold=True,size=13)
hdr=['악기','곡 수','CP ↑','CP활성 ↑','PCHE차이 ↓','PCH유사 ↑','GS차이 ↓','GS일치 ↑','마디당 음 (원)','마디당 음 (생)','빈 마디 (원)','빈 마디 (생)']
ws.append([]); ws.append(hdr)
for c in ws[3]: c.font=F(bold=True,color='FFFFFF'); c.fill=HF; c.alignment=Alignment(horizontal='center',vertical='center',wrap_text=True); c.border=B
for k,(inst,ko) in enumerate(insts):
    r=4+k; ws.cell(r,1,ko).font=F(bold=True); ws.cell(r,2,f"=COUNT('{ko}'!B2:B21)").font=F()
    for j,h in enumerate(hdr[2:],3):
        v=avg_ref.get((ko,h)); c=ws.cell(r,j,v if v else '–'); c.font=F()
        c.number_format='0' if '빈 마디' in h else ('0.0' if '마디당' in h else '0.00')
    for j in range(1,13): ws.cell(r,j).border=B; ws.cell(r,j).alignment=Alignment(horizontal='center')
notes=['읽는 법',
 '· CP: 코드(화성) 일치도, MIDI-RWKV 정의. CP활성: 원래 파트가 소리 나는 구간에서만 계산',
 '· PCHE차이: 음이름 분포 엔트로피(조성감) 차이. PCH유사: 음이름 분포 코사인 유사도',
 '· GS차이: 리듬 일관성(Groove Consistency) 차이. GS일치: 같은 마디의 음 시작 위치 일치도',
 '· F1·Jaccard는 원곡 복원도라 생성 모델에는 참고용 (낮아도 정상, 베끼지 않았다는 뜻)',
 '· 드럼은 음 높이가 타악기 종류라 CP·PCHE·PCH 계산 안 함',
 '· 원래 파트 빈 마디가 많은 곡은 CP가 낮게 나옴 → CP활성 기준으로 해석',
 '· 생성 쪽 빈 마디는 GS를 부풀리고 CP를 낮춤 (긴 곡·트랙 많을 때 토큰 한계 영향)',
 '· 빈칸: 베이스 Track00017(원곡에 베이스 없음), 드럼 Track00008(생성 실패)',
 '· 네 악기 고르게 괜찮은 곡: Track00001, 00008, 00010, 00011']
for i,t in enumerate(notes): c=ws.cell(10+i,1,t); c.font=F(bold=(i==0),size=10)
ws.column_dimensions['A'].width=10
for j in range(2,13): ws.column_dimensions[L(j)].width=12
ws.row_dimensions[3].height=32
wb.save(OUT); print('저장:', OUT)
