# Splice the new scene 5 (refund role check) into the November 24 video.
import subprocess,sys
# Usage: python splice_scene5.py NOV24_CUT.mp4 OLD_CAPTIONS.srt s5_audio.wav out.mp4 [tail_s]
# Needs screen5.mp4 and V.txt (scene start in screen5.mp4, from the magenta sync flash) in the cwd.
SRC=sys.argv[1]; OLDSRT=sys.argv[2]
AUD=sys.argv[3]; OUT=sys.argv[4]; LEAD=0.8; TAIL=float(sys.argv[5]) if len(sys.argv)>5 else 0.9
A_END=98.606; B_START=111.65   # old scene 5 = [A_END, B_START)
V=float(open('V.txt').read())
dur=lambda f:float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',f]))
L=dur(AUD); S=LEAD+L+TAIL; src=dur(SRC); total=A_END+S+(src-B_START); delta=S-(B_START-A_END)
print('clip',round(L,2),'scene',round(S,2),'total',round(total,2))
assert total<=149.8, 'too long'
text="Being on the record isn't enough: each amount must also play the right role. This draft gives the two-hundred-dollar payment as the refund, which was fifty, so it is rejected and repaired."
chunks=["Being on the record isn't enough:","each amount must also play the right role.","This draft gives the two-hundred-dollar payment as the refund,","which was fifty, so it is rejected and repaired."]
ts=lambda x:f'{int(x//3600):02}:{int(x%3600//60):02}:{int(x%60):02},{int(round(x*1000)%1000):03}'
def parse(t):h,m,s=t.split(':');s,ms=s.split(',');return int(h)*3600+int(m)*60+int(s)+int(ms)/1000
# scene-local captions
tot=sum(len(c) for c in chunks);t=LEAD;loc=[]
for c in chunks: e=t+L*len(c)/tot;loc.append((t,e-0.05,c));t=e
open('s5.srt','w').write('\n'.join(f'{i+1}\n{ts(a)} --> {ts(b)}\n{c}\n' for i,(a,b,c) in enumerate(loc)))
# full captions: old ones before/after, shifted
old=open(OLDSRT).read().strip().split('\n\n')
ent=[]
for blk in old:
    l=blk.split('\n');a,b=[parse(x.strip()) for x in l[1].split('-->')];txt='\n'.join(l[2:])
    if b<=A_END: ent.append((a,b,txt))
    elif a>=B_START-1: ent.append((a+delta,b+delta,txt))
ent=[e for e in ent if e[1]<=A_END]+[(A_END+a,A_END+b,c) for a,b,c in loc]+[e for e in ent if e[0]>A_END]
open('captions.srt','w').write('\n'.join(f'{i+1}\n{ts(a)} --> {ts(b)}\n{c}\n' for i,(a,b,c) in enumerate(ent)))
style="FontName=Inter,FontSize=13,PrimaryColour=&H00FFFFFF,BackColour=&H80000000,OutlineColour=&H80000000,BorderStyle=3,Outline=6,Shadow=0,MarginV=14"
# new scene: video + captions + audio
subprocess.run(['ffmpeg','-v','error','-y','-ss',f'{V:.3f}','-t',f'{S:.3f}','-i','screen5.mp4','-i',AUD,
 '-filter_complex',f"[0:v]fps=30,scale=1920:1080,subtitles=s5.srt:force_style='{style}',format=yuv420p[v];[1:a]aresample=48000,loudnorm=I=-16:TP=-1.5,aresample=48000,adelay={int(LEAD*1000)}|{int(LEAD*1000)},apad,atrim=0:{S:.3f}[a]",
 '-map','[v]','-map','[a]','-ac','2','-c:v','libx264','-crf','16','-preset','medium','-c:a','pcm_s16le','scene5.mkv'],check=True)
subprocess.run(['ffmpeg','-v','error','-y','-i',SRC,'-i','scene5.mkv','-filter_complex',
 f"[0:v]trim=0:{A_END},setpts=PTS-STARTPTS[v0];[0:a]atrim=0:{A_END},asetpts=PTS-STARTPTS,aresample=48000[a0];"
 f"[1:v]setpts=PTS-STARTPTS[v1];[1:a]asetpts=PTS-STARTPTS[a1];"
 f"[0:v]trim=start={B_START},setpts=PTS-STARTPTS[v2];[0:a]atrim=start={B_START},asetpts=PTS-STARTPTS,aresample=48000[a2];"
 "[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[v][a]",'-map','[v]','-map','[a]','-c:v','libx264','-crf','20','-preset','medium','-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-ac','2','-movflags','+faststart',OUT],check=True)
print('done',dur(OUT))
