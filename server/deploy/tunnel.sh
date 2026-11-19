#!/bin/bash
# 노트북 8081(클러스터 rocky-api port-forward) → 팀 서버 127.0.0.1:18081. 끊기면 3초 뒤 다시 연결.
while true; do
  ssh -N -o BatchMode=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
      -o ExitOnForwardFailure=yes -R 127.0.0.1:18081:127.0.0.1:8081 swpp-b
  echo "$(date +%T) tunnel exited, retrying"; sleep 3
done
