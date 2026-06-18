from flask import Flask, render_template, request, redirect, session, url_for
from flask_socketio import SocketIO, join_room, leave_room, emit
import requests
import urllib.parse
from yt_dlp import YoutubeDL
import static_ffmpeg
import os

# 🛠️ Render 서버 내부 멀티미디어 디코더(FFmpeg) 강제 이식
static_ffmpeg.add_paths()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'music_secret_key_1234'
socketio = SocketIO(app, cors_allowed_origins="*")

# 🔑 디스코드 OAuth2 설정
DISCORD_CLIENT_ID = '1516847818344497243'
DISCORD_CLIENT_SECRET = 'WMM8U0_CvMzNJpsy7cYcnLCVTXvn3oIc'
DISCORD_REDIRECT_URI = 'https://music-azit.onrender.com/callback'

# ⭐ 절대 마스터 닉네임 설정
MASTER_NAME = "종민" 

# 단일 채널용 실시간 메모리 데이터셋
AZIT_DATA = {
    'users': [],
    'owner': None,   # 임명된 방장
    'master': None,  # 절대 권력 마스터 (방장님)
    'queue': [],
    'current_song': None
}

@app.route('/')
def index():
    user_info = session.get('user')
    return render_template('index.html', user=user_info)

@app.route('/login')
def login():
    redirect_uri_encoded = urllib.parse.quote(DISCORD_REDIRECT_URI, safe='')
    discord_login_url = f"https://discord.com/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={redirect_uri_encoded}&response_type=code&scope=identify"
    return redirect(discord_login_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code: 
        return "로그인 실패", 400
        
    token_url = 'https://discord.com/api/v10/oauth2/token'
    data = {
        'client_id': DISCORD_CLIENT_ID, 
        'client_secret': DISCORD_CLIENT_SECRET, 
        'grant_type': 'authorization_code', 
        'code': code, 
        'redirect_uri': DISCORD_REDIRECT_URI
    }
    
    token_json = requests.post(token_url, data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'}).json()
    access_token = token_json.get('access_token')
    if not access_token: 
        return "토큰 발급 실패", 400
        
    user_json = requests.get('https://discord.com/api/v10/users/@me', headers={'Authorization': f'Bearer {access_token}'}).json()
    
    discord_id = user_json.get('id')
    username = user_json.get('global_name') or user_json.get('username')
    avatar_hash = user_json.get('avatar')
    avatar_url = f"https://cdn.discordapp.com/avatars/{discord_id}/{avatar_hash}.png" if avatar_hash else "https://cdn.discordapp.com/embed/avatars/0.png"
    
    session['user'] = {'id': discord_id, 'name': username, 'avatar': avatar_url}
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))


# 📡 1. 실시간 음악 검색 파이프라인 (속도 다이어트 옵션 고정)
@socketio.on('search_song')
def on_search_song(data):
    keyword = data.get('keyword', '').strip()
    if not keyword: 
        return
        
    try:
        # ⚡ 검색 전용 초경량 다이어트 바구니
        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'skip_download': True,
            'extract_flat': 'in_playlist',  # 껍데기 정보만 광속으로 파싱
            'force_generic_extractor': False,
        }
        
        with YoutubeDL(ydl_opts) as ydl:
            search_result = ydl.extract_info(f"ytsearch5:{keyword}", download=False)
            results = []
            if 'entries' in search_result:
                for entry in search_result['entries']:
                    if not entry: 
                        continue
                    results.append({
                        'title': entry.get('title'),
                        'url': f"https://www.youtube.com/watch?v={entry.get('id')}",
                        'thumbnail': f"https://i.ytimg.com/vi/{entry.get('id')}/hqdefault.jpg"
                    })
            emit('search_result', {'results': results})
    except Exception as e: 
        print(f"🚨 검색 실패: {e}")


# 📡 2. 대기열 및 재생 제어 파이프라인 (유튜브 차단 우회 및 포맷 에러 고정)
@socketio.on('music_control')
def on_music_control(data):
    action = data.get('action')
    
    if action == 'load':
        url = data.get('url', '')
        thumbnail = data.get('thumbnail', '')
        try:
            # 🍪 실제 재생 시 봇 인증을 무력화하는 무적의 우회 바구니
            ydl_opts = {
                'format': 'ba/ba*',
                'noplaylist': True,
                'quiet': True,
                'skip_download': True,
                
                # 🍪 기존 쿠키 라인 유지
                'cookiefile': os.path.join(os.path.dirname(__file__), 'cookies.txt'), 
                
                # 🎯 [2026 최신 차단 파괴 옵션] 유튜브의 기기 인증 토큰(POToken)을 강제로 생성 및 주입합니다.
                'extractor_args': {
                    'youtube': {
                        'player_client': ['web', 'ios'],  # 폰(iOS)에서 요청하는 것처럼 위장해서 락을 해제
                        'po_token': ['web+https://www.youtube.com/checkpoint'],
                    }
                },
                
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1',
                }
            }
            
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                song_data = {
                    'audioUrl': info['url'], 
                    'title': info.get('title', '유튜브 오디오'), 
                    'thumbnail': thumbnail,
                    'progress': 0  # 싱크 최적화용 0초 초기화
                }
                AZIT_DATA['queue'].append(song_data)
                send_queue_update()
                if AZIT_DATA['current_song'] is None:
                    play_next_song()
        except Exception as e:
            print(f"🚨 음원 추출 실패 상세 로그: {e}")
            emit('status', {'msg': "❌ 음원 추출에 실패했습니다."}, to='main_azit')
    
    elif action == 'sync_time':
        if AZIT_DATA['current_song']:
            AZIT_DATA['current_song']['progress'] = data.get('currentTime', 0)

    elif action in ['pause', 'resume']:
        emit('music_broadcast', {'action': action}, to='main_azit')
        
    elif action == 'skip':
        play_next_song()
        
    elif action == 'delete':
        idx = data.get('index')
        if 0 <= idx < len(AZIT_DATA['queue']):
            del_title = AZIT_DATA['queue'][idx]['title']
            del AZIT_DATA['queue'][idx]
            emit('status', {'msg': f"🗑️ 대기열에서 [{del_title}] 곡이 삭제되었습니다."}, to='main_azit')
            send_queue_update()
            
    elif action == 'move':
        idx = data.get('index')
        direction = data.get('direction')
        q = AZIT_DATA['queue']
        if direction == 'up' and idx > 0: 
            q[idx], q[idx-1] = q[idx-1], q[idx]
        elif direction == 'down' and idx < len(q) - 1: 
            q[idx], q[idx+1] = q[idx+1], q[idx]
        send_queue_update()


# 👑 방장 권한 제어 관련 로직
@socketio.on('transfer_owner')
def on_transfer_owner(data):
    target_user = data.get('to')
    if target_user in AZIT_DATA['users']:
        AZIT_DATA['owner'] = target_user
        emit('status', {'msg': f"👑 마스터에 의해 {target_user}님이 새로운 방장으로 지정되었습니다!"}, to='main_azit')
        send_room_status()

def play_next_song():
    if AZIT_DATA['queue']:
        next_song = AZIT_DATA['queue'].pop(0)
        AZIT_DATA['current_song'] = next_song
        emit('music_broadcast', {
            'action': 'load', 
            'audioUrl': next_song['audioUrl'], 
            'title': next_song['title'], 
            'thumbnail': next_song['thumbnail']
        }, to='main_azit')
    else:
        AZIT_DATA['current_song'] = None
        emit('music_broadcast', {'action': 'stop_all'}, to='main_azit')
    send_queue_update()

def send_queue_update():
    socketio.emit('queue_update', {
        'queue': AZIT_DATA['queue'], 
        'current_song': AZIT_DATA['current_song']
    }, to='main_azit')


# 📡 단일 채널 실시간 다이렉트 입장 로직
@socketio.on('join_azit')
def on_join_azit(data):
    username = data.get('username', '손님').strip()
    join_room('main_azit')
    
    # 👑 절대 마스터 자동 매칭
    if username == MASTER_NAME:
        AZIT_DATA['master'] = username
        AZIT_DATA['owner'] = username
    
    if username not in AZIT_DATA['users']:
        AZIT_DATA['users'].append(username)
        
    # 최초 개설자 방장 자동 임명 방어 코드
    if AZIT_DATA['owner'] is None and AZIT_DATA['master'] != username:
        AZIT_DATA['owner'] = username
        
    send_room_status()
    send_queue_update()
    
    if AZIT_DATA['current_song']:
        curr = AZIT_DATA['current_song']
        emit('music_broadcast', {
            'action': 'load', 
            'audioUrl': curr['audioUrl'], 
            'title': curr['title'], 
            'thumbnail': curr['thumbnail'],
            'seekTo': curr['progress']  # 중간 진입 시 동시 싱크 타임워프
        }, to=request.sid)
        
    emit('status', {'msg': f"📣 {username}님이 아지트에 합류했습니다."}, to='main_azit')

@socketio.on('disconnect')
def on_disconnect():
    pass

def send_room_status():
    socketio.emit('room_update', {
        'users': AZIT_DATA['users'], 
        'owner': AZIT_DATA['owner'], 
        'master': AZIT_DATA['master']
    }, to='main_azit')


if __name__ == '__main__':
    # Render 동적 포트 자동 바인딩 (없으면 기본 5000포트)
    port = int(os.environ.get("PORT", 5000))
    # host="0.0.0.0"을 선언해야 내부망 포트가 정상 작동합니다.
    socketio.run(app, host="0.0.0.0", port=port, debug=False)