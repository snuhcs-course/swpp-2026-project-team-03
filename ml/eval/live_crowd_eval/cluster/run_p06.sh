#!/bin/bash
# P06 원인 확인용: 관중 구간 목록 + 원본/cleaned2를 각각 BS-RoFormer로 분리한 베이스 stem + 청취용 음원
# 결과: /data/live_eval/p06/ → p06.tgz
set -uo pipefail
E=/data/live_eval; O=$E/p06; mkdir -p $O
export HF_HOME=/data/cache/hf TORCH_HOME=/data/cache/torch XDG_CACHE_HOME=/data/cache/xdg
PY=/data/rocky-unified/.venv/bin/python
log() { echo "=== $(date '+%F %T') $*"; }
$PY - <<'PYEOF'
import numpy as np, soundfile as sf
E='/data/live_eval'; O=E+'/p06'
mix,sr=sf.read(E+'/wav/P06.wav',always_2d=True); cr,_=sf.read(E+'/crowd/crowd/P06.flac',always_2d=True)
c2,_=sf.read(E+'/crowd/cleaned2/P06.wav',always_2d=True)
n=min(len(mix),len(cr)); mix,cr=mix[:n],cr[:n]; mu=mix-cr; secs=n//sr
e=lambda x: np.mean(x[:secs*sr].reshape(secs,sr,2)**2,axis=(1,2))+1e-12
rel=10*np.log10(e(cr)/e(mu)); lvl=10*np.log10(e(mix))
with open(O+'/segments.csv','w') as f:
    f.write('sec,crowd_minus_music_db,mix_level_db,music_level_db\n')
    for s in range(secs): f.write(f"{s},{rel[s]:.1f},{lvl[s]:.1f},{10*np.log10(e(mu)[s]):.1f}\n")
sf.write(O+'/original.flac',mix,sr,subtype='PCM_24')
sf.write(O+'/crowd.flac',cr,sr,subtype='PCM_24')
pk=float(np.abs(c2).max()); sf.write(O+'/cleaned2_scaled.flac',c2/max(pk,1.0),sr,subtype='PCM_24')
print('P06 peak cleaned2',pk,'crowd secs',[int(s) for s in np.where((rel>=6)&(lvl>-60))[0]])
PYEOF
for arm in A C; do
  if [ $arm = A ]; then in=$E/wav/P06.wav; else in=$E/crowd/cleaned2/P06.wav; fi
  log "P06 $arm 분리"; tmp=$E/_sep_p06_$arm
  $PY /data/pipeline/separate_bs_roformer.py $in $tmp --models-dir /data/bsrofo/models --lib-dir /data/bsrofo/pylib > $O/sep_$arm.log 2>&1 || log "분리 실패 $arm"
  $PY -c "import soundfile as sf,sys; x,sr=sf.read(sys.argv[1]); sf.write(sys.argv[2],x,sr,subtype='PCM_24')" $tmp/bass.wav $O/bass_stem_$arm.flac
  rm -rf $tmp
done
cp $E/out/C/P06/note_gate.json $O/note_gate_C.json; cp $E/out/A/P06/note_gate.json $O/note_gate_A.json
cp $E/out/C/P06/input_check.json $O/input_check_C.json
cd $E && tar czf p06.tgz p06 && rm -rf parts && mkdir parts && split -b 5m p06.tgz parts/q_ && ls parts | wc -l
log "ALL DONE — p06.tgz. Pod 지우기: k22 delete pod rocky-live-p06"
