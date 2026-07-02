PS C:\Users\jagan\dog-ai\dog-ai> .\venv\Scripts\python pipeline.py
[Pipeline] Prior session log archived → terminal_output_2026-04-28_234738.md
[Pipeline] Starting...
[Vision] Camera 0 opened (1280x720) via DirectShow
[Vision] RetinaFace (buffalo_l) loaded on GPU
[Vision] AdaFace loaded on GPU
[Pipeline] Preloading audio models...
[Audio] Loading Whisper large-v3-turbo on GPU...
[Audio] Whisper ready — 3.4s
[Audio] Loading Kokoro TTS...
[Audio] Kokoro ready — 0.9s
[Audio] Smart-Turn loaded — neural end-of-turn active
[Voice] Loading ECAPA-TDNN speaker embedder...
[Voice] ECAPA-TDNN ready — 0.7s
[Voice] Gallery loaded — 0 person(s) with voice profiles
[Vision] MiniFASNet anti-spoofing loaded (2 models, device=cuda)
Loading weights: 100%|█████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 105/105 [00:00<00:00, 30709.29it/s]
[EmotionAgent] j-hartmann/emotion-english-distilroberta-base loaded on CPU (shared)
[BrainAgent] Graph schema v0→v2: wiping Kuzu graph for rebuild with new schema
[Pipeline] All systems ready. Watching...
[BrainAgent] Started — watching conversation_log for new turns
[Vision] none
[Vision] Active (WATCHING) — no face
[Audio] Listening...
[Audio] Speech started (chunk #850, 00:05:28.856)
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Smart-Turn: turn complete (p=0.85, grace=0.48s)
[Audio] Turn end — 7 speech chunks, 0 lip extension(s)
[Vision] Active (WATCHING) — unrecognized
[STT] 00:05:31.736 (387ms) 'Okay.'
[Pipeline] Voice-first: heard speech — identifying speaker...
[Pipeline] State: WATCHING -> SPEAKING
[Audio] TTS 00:05:32.012: 'Hey there... are you my best friend?'
[Pipeline] State: SPEAKING -> LISTENING
[Audio] Listening...
[Audio] Speech started (chunk #19, 00:05:35.648)
[Audio] Echo skip: 7/19 pre-roll chunks trimmed
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Smart-Turn: turn complete (p=0.94, grace=0.48s)
[Audio] Turn end — 16 speech chunks, 0 lip extension(s)
[STT] 00:05:37.675 (229ms) 'Yeah, yes I am.'
[Audio] TTS 00:05:37.675: 'Wow! What's your name?'
[Audio] Listening...
[Audio] Speech started (chunk #18, 00:05:40.398)
[Audio] Echo skip: 7/18 pre-roll chunks trimmed
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Smart-Turn: turn complete (p=0.97, grace=0.19s)
[Audio] Turn end — 19 speech chunks, 0 lip extension(s)
[STT] 00:05:42.190 (216ms) 'My name is Jagan.'
[Pipeline] State: LISTENING -> ENROLLING
[Audio] TTS 00:05:42.196: 'Wait, let me see you clearly, Jagan... I want to remember you from now on.'
[Audio] TTS 00:05:54.245: 'Got you, Jagan! From now on, you're my best friend. I'll never forget you.'
[Vision] Background: recognized Jagan (score=0.911) — waking pipeline
[Pipeline] Best friend enrolled: Jagan (jagan_992ed5) with 20 embeddings
[Pipeline] State: ENROLLING -> WATCHING
[Pipeline] Anti-spoof: PASSED Jagan
[Room] New room session: room_1777401359_b9cdb5
[Room] Participant joined: Jagan (jagan_992ed5) → room_1777401359_b9cdb5 (now 1 participant(s))
[Session] Open: jagan_992ed5 (face) — Jagan
[Vision] Jagan
[Vision] Active (WATCHING) — Jagan
[Vision] none
[Vision] Jagan
[Brain] Greeting generation failed (All connection attempts failed) — using fallback
[Audio] TTS 00:06:05.828: 'Good to see you, Jagan, even at this hour.'
[Vision] none
[Pipeline] State: WATCHING -> LISTENING
[Pipeline] Listening for Jagan...
[Audio] Listening...
[Vision] Jagan
[Audio] Speech started (chunk #71, 00:06:11.625)
[Vision] none
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Smart-Turn: turn complete (p=0.98, grace=0.19s)
[Audio] Turn end — 52 speech chunks, 0 lip extension(s)
[Vision] Jagan
[STT] 00:06:15.186 (275ms) 'yeah what is your name by the way what should I call you'
[Audio] Listening...
[Pipeline] State: LISTENING -> THINKING
[Voice] Loading pyannote speaker-diarization-3.1...
[Vision] none
[Vision] Jagan
[Voice] pyannote ready — 5.6s
[Voice] diarize: pyannote returned 1 segment(s)
[Voice] 00:06:21.772 Routing: current — voice ambiguous, no other candidates in scene
[STT] Jagan: yeah what is your name by the way what should I call you
[Pipeline] Turn start 00:06:21.774: Jagan — 'yeah what is your name by the way what should I call you'
[BrainAgent] Spawn (background): autocompact for Jagan
[Privacy] 00:06:21.794 query_knowledge_for requester='jagan_992ed5' (owner-mode) entity='Jagan' → 0 row(s)
[BrainAgent] Spawn (background): emotion process_turn for Jagan
[Brain] Context: history=0 turns, memory=no, emotion=no, room=no, scene=yes
[Pipeline] State: THINKING -> SPEAKING
[Brain] Context built: 1 messages, ~20 tokens
[Brain] Streaming meta-llama/Llama-3.3-70B-Instruct-Turbo... (~6,301 tokens)
[Vision] none
[Voice] Profile updated for jagan_992ed5 (1/20 voice samples) [via face_witness]
[Vision] Jagan
[Brain] 00:06:23.663 Tool: update_system_name({'name': 'none'})
[classifier_graph] loading local E5 (intfloat/multilingual-e5-large-instruct) on cuda...
[Vision] none
Loading weights: 100%|█████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 391/391 [00:00<00:00, 10153.94it/s]
[Vision] Jagan
[classifier_graph] local E5 loaded (4.7s on cuda)
[classifier_graph] latency 5673ms > 100ms budget on 'yeah what is your name by the way what should I call you'
[Intent] shadow divergence: graph='assign_system_name' (conf=0.56) vs llm='casual_conversation' (conf=0.80)
[Intent] 00:06:29.341 tools=[update_system_name] classified=casual_conversation value=None conf=0.80 reason="The user is asking about the AI's name, but the tone is casual and inquiring, ra"
[Pipeline] Tool: update_system_name rejected invalid name 'none'
[Pipeline] Turn addressed: Jagan (default; candidates=1)
[BrainAgent] Notify — waking agent loop
[Audio] TTS 00:06:29.343: 'What name would you like to give me?'
[BrainAgent] 00:06:29.344 Triage: PASS turn 1 — processing (role=user, words=13, person_type=best_friend)
[Vision] none
[BrainAgent] Extraction: no facts found in turn 1 (1746ms)
[BrainAgent] 00:06:31.091 Triage: SKIP turn 2 — assistant turn (role=assistant, words=8, person_type=best_friend)
[Vision] Active (SPEAKING) — Jagan
[Pipeline] Turn end 00:06:32.023: Jagan — 36 chars
[Pipeline] State: SPEAKING -> LISTENING
[Pipeline] Listening for Jagan...
[Audio] Listening...
[Audio] Speech started (chunk #33, 00:06:33.331)
[Audio] Echo skip: 5/31 pre-roll chunks trimmed
[Vision] Jagan
[Audio] Silence detected — waiting for end-of-turn...
[Vision] none
[Audio] Smart-Turn: turn complete (p=0.85, grace=0.48s)
[Audio] Turn end — 40 speech chunks, 0 lip extension(s)
[STT] 00:06:36.929 (336ms) 'Kara, how is it? I will call you Kara from now on.'
[Audio] Listening...
[Pipeline] State: LISTENING -> THINKING
[Voice] diarize: pyannote returned 1 segment(s)
[Voice] 00:06:37.564 Routing: current — jagan_992ed5 (score=0.579)
[Voice] diarize: pyannote returned 1 segment(s)
[STT] Jagan (voice=0.58): Kara, how is it? I will call you Kara from now on.
[Pipeline] Turn start 00:06:37.624: Jagan — 'Kara, how is it? I will call you Kara from now on.'
[BrainAgent] Spawn (background): autocompact for Jagan
[Privacy] 00:06:37.626 query_knowledge_for requester='jagan_992ed5' (owner-mode) entity='Jagan' → 0 row(s)
[BrainAgent] Spawn (background): emotion process_turn for Jagan
[Brain] Context: history=2 turns, memory=no, emotion=no, room=no, scene=yes
[Pipeline] State: THINKING -> SPEAKING
[Brain] Context built: 3 messages, ~52 tokens
[Brain] Streaming meta-llama/Llama-3.3-70B-Instruct-Turbo... (~6,342 tokens)
[Voice] Profile updated for jagan_992ed5 (2/20 voice samples) [via face_witness]
[Brain] 00:06:38.999 Tool: update_system_name({'name': 'Kara'})
[Intent] 00:06:40.630 tools=[update_system_name] classified=assign_system_name value='Kara' conf=0.95 reason="The user explicitly assigns the name 'Kara' to the AI, indicating a clear intent"
[Pipeline] Tool: update_system_name allowed by intent gate — intent match
[Pipeline] Tool: system name → 'Kara'
[Pipeline] Turn addressed: Jagan (default; candidates=1)
[BrainAgent] Notify — waking agent loop
[Audio] TTS 00:06:40.646: 'Got it, I'll go by Kara.'
[BrainAgent] 00:06:40.647 Triage: PASS turn 3 — processing (role=user, words=12, person_type=best_friend)
[BrainAgent] Extraction: no facts found in turn 3 (1807ms)
[BrainAgent] 00:06:42.471 Triage: SKIP turn 4 — assistant turn (role=assistant, words=6, person_type=best_friend)
[Vision] Person left frame: Jagan (conf=0.58)
[Pipeline] Turn end 00:06:43.014: Jagan — 24 chars
[Pipeline] State: SPEAKING -> LISTENING
[Pipeline] Listening for Jagan...
[Audio] Listening...
[Vision] Jagan
[Audio] Speech started (chunk #37, 00:06:44.451)
[Audio] Echo skip: 1/31 pre-roll chunks trimmed
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Silence detected — waiting for end-of-turn...
[Vision] none
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Smart-Turn: turn complete (p=0.98, grace=0.19s)
[Audio] Turn end — 78 speech chunks, 0 lip extension(s)
[STT] 00:06:48.941 (314ms) 'Okay Kara, tell me what all you can do, what are all your capabilities?'
[Audio] Listening...
[Vision] Jagan
[Vision] none
[Pipeline] State: LISTENING -> THINKING
[Voice] diarize: pyannote returned 1 segment(s)
[Voice] 00:06:49.566 Routing: current — jagan_992ed5 (score=0.707)
[Voice] diarize: pyannote returned 1 segment(s)
[STT] Jagan (voice=0.71): Okay Kara, tell me what all you can do, what are all your capabilities?
[Pipeline] Turn start 00:06:49.625: Jagan — 'Okay Kara, tell me what all you can do, what are all your ca...'
[BrainAgent] Spawn (background): autocompact for Jagan
[Privacy] 00:06:49.628 query_knowledge_for requester='jagan_992ed5' (owner-mode) entity='Jagan' → 0 row(s)
[BrainAgent] Spawn (background): emotion process_turn for Jagan
[Brain] Context: history=4 turns, memory=no, emotion=yes, room=no, scene=yes
[Pipeline] State: THINKING -> SPEAKING
[Brain] Context built: 5 messages, ~86 tokens
[Brain] Streaming meta-llama/Llama-3.3-70B-Instruct-Turbo... (~6,681 tokens)
[Voice] Profile updated for jagan_992ed5 (3/20 voice samples) [via face_witness]
[Brain] 00:06:52.247 search_web REJECTED — user turn contains no live-data marker — answer from knowledge: 'Kara capabilities'
[Audio] TTS stream 00:06:54.662: 'I can see and recognize faces, hear and identify voices, and remember our conversations.'
[Vision] Person left frame: Jagan (conf=0.71)
[Audio] TTS stream 00:06:56.248: 'I can also search the web for information and answer questions to the best of my ability.'
[Vision] Jagan
[Vision] none
[Audio] Playback complete — echo window reset (00:07:02.162)
[Audio] Playback complete — echo window reset (00:07:07.393)
[Pipeline] Turn addressed: Jagan (default; candidates=1)
[BrainAgent] Notify — waking agent loop
[Pipeline] Turn end 00:07:07.394: Jagan — 178 chars
[Pipeline] State: SPEAKING -> LISTENING
[Pipeline] Listening for Jagan...
[Pipeline] Session expired: Jagan (jagan_992ed5)
[BrainAgent] Session end: Jagan (jagan_992ed5) — launching async tasks
[BrainAgent] Notify — waking agent loop
[Session] Close: jagan_992ed5 — Jagan
[Room] Room session ended: room_1777401359_b9cdb5
[Audio] Listening...
[Room] Room-end hook fired for room_1777401359_b9cdb5 (participants=1, duration=67s)
[Room] Synthesis skipped for room_1777401359_b9cdb5 — single-speaker (per-person session-end already handled it)
[BrainAgent] 00:07:07.401 Triage: PASS turn 5 — processing (role=user, words=14, person_type=best_friend)
[Audio] Speech started (chunk #25, 00:07:08.449)
[Audio] Echo skip: 7/25 pre-roll chunks trimmed
[Audio] Silence detected — waiting for end-of-turn...
[BrainAgent] Extraction: no facts found in turn 5 (1312ms)
[BrainAgent] 00:07:08.715 Triage: SKIP turn 6 — assistant turn (role=assistant, words=31, person_type=best_friend)
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Turn end — 33 speech chunks, 0 lip extension(s)
[PromptPrefAgent] Jagan: activated (new) [prompt_agent] — [greeting_style] Prefers informal, casual greetings — use a friendly tone when addressing them
[STT] 00:07:11.526 (220ms) 'Okay, do you know where I live?'
[Audio] Listening...
[PromptPrefAgent] Jagan: activated (new) [prompt_agent] — [communication_style] Prefers direct and casual communication — use simple language and avoid formal tone
[PromptPrefAgent] Jagan: activated (new) [prompt_agent] — [response_length] Prefers brief responses — keep initial replies concise, but provide more information when asked
[Pipeline] State: LISTENING -> THINKING
[Voice] diarize: pyannote returned 1 segment(s)
[Voice] 00:07:12.140 Routing: switch_enrolled → jagan_992ed5 (score=0.644)
[Voice] diarize: pyannote returned 1 segment(s)
[Room] New room session: room_1777401432_0cb587
[Room] Participant joined: Jagan (jagan_992ed5) → room_1777401432_0cb587 (now 1 participant(s))
[Session] Open: jagan_992ed5 (voice) — Jagan
[Voice] Speaker switch → Jagan (score=0.644)
[STT] Jagan (voice=0.64): Okay, do you know where I live?
[Pipeline] Turn start 00:07:12.210: Jagan — 'Okay, do you know where I live?'
[BrainAgent] Spawn (background): autocompact for Jagan
[Privacy] 00:07:12.212 query_knowledge_for requester='jagan_992ed5' (owner-mode) entity='Jagan' → 0 row(s)
[BrainAgent] Spawn (background): emotion process_turn for Jagan
[Brain] Context: history=6 turns, memory=no, emotion=no, room=no, scene=yes
[Pipeline] State: THINKING -> SPEAKING
[Voice] Refused accumulation for jagan_992ed5: no witness (face_conf=0.00, age=1777401432.2s, voice_n=3, voice_conf=0.64, bootstrap=0)
[Brain] Context built: 7 messages, ~170 tokens
[Brain] Streaming meta-llama/Llama-3.3-70B-Instruct-Turbo... (~6,753 tokens)
[Vision] Jagan
[Brain] 00:07:13.737 Tool: search_memory('Jagan', 'home')
[Privacy] 00:07:13.738 query_knowledge_for requester='jagan_992ed5' (owner-mode) entity='Jagan' → 0 row(s)
[Vision] none
[Audio] TTS stream 00:07:15.219: 'I don't have details about that.'
[Vision] Jagan
[Audio] Playback complete — echo window reset (00:07:17.594)
[Pipeline] Turn addressed: Jagan (default; candidates=1)
[BrainAgent] Notify — waking agent loop
[Pipeline] Turn end 00:07:17.595: Jagan — 32 chars
[Pipeline] State: SPEAKING -> LISTENING
[Pipeline] Listening for Jagan...
[Audio] Listening...
[BrainAgent] 00:07:17.600 Triage: PASS turn 7 — processing (role=user, words=7, person_type=best_friend)
[Audio] Speech started (chunk #29, 00:07:18.809)
[Audio] Echo skip: 6/29 pre-roll chunks trimmed
[Audio] Silence detected — waiting for end-of-turn...
[Vision] none
[BrainAgent] Extraction: no facts found in turn 7 (2195ms)
[BrainAgent] 00:07:19.796 Triage: SKIP turn 8 — assistant turn (role=assistant, words=6, person_type=best_friend)
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Smart-Turn: turn complete (p=0.93, grace=0.48s)
[Audio] Turn end — 50 speech chunks, 0 lip extension(s)
[Vision] Jagan
[STT] 00:07:22.762 (259ms) 'Okay, I am from India, Andhra Pradesh, Tirupati.'
[Audio] Listening...
[Vision] none
[Pipeline] State: LISTENING -> THINKING
[Voice] diarize: pyannote returned 1 segment(s)
[Voice] 00:07:23.408 Routing: current — jagan_992ed5 (score=0.801)
[Voice] diarize: pyannote returned 1 segment(s)
[STT] Jagan (voice=0.80): Okay, I am from India, Andhra Pradesh, Tirupati.
[Pipeline] Turn start 00:07:23.467: Jagan — 'Okay, I am from India, Andhra Pradesh, Tirupati.'
[BrainAgent] Spawn (background): autocompact for Jagan
[Privacy] 00:07:23.471 query_knowledge_for requester='jagan_992ed5' (owner-mode) entity='Jagan' → 0 row(s)
[BrainAgent] Spawn (background): emotion process_turn for Jagan
[Brain] Context: history=8 turns, memory=no, emotion=no, room=no, scene=yes
[Pipeline] State: THINKING -> SPEAKING
[Voice] Refused accumulation for jagan_992ed5: no witness (face_conf=0.87, age=1.1s, voice_n=3, voice_conf=0.80, bootstrap=0)
[Brain] Context built: 9 messages, ~200 tokens
[Brain] Streaming meta-llama/Llama-3.3-70B-Instruct-Turbo... (~6,748 tokens)
[Vision] Jagan
[Brain] 00:07:25.367 Tool: search_memory('Jagan', 'location')
[Privacy] 00:07:25.367 query_knowledge_for requester='jagan_992ed5' (owner-mode) entity='Jagan' → 0 row(s)
[Vision] none
[Audio] TTS stream 00:07:27.523: 'Tirupati, that's a beautiful place, I'll remember that you're from there.'
[Vision] Person left frame: Jagan (conf=0.82)
[Audio] Playback complete — echo window reset (00:07:32.473)
[Pipeline] Turn addressed: Jagan (default; candidates=1)
[BrainAgent] Notify — waking agent loop
[Pipeline] Turn end 00:07:32.474: Jagan — 73 chars
[Pipeline] State: SPEAKING -> LISTENING
[Pipeline] Listening for Jagan...
[Audio] Listening...
[BrainAgent] 00:07:32.479 Triage: PASS turn 9 — processing (role=user, words=8, person_type=best_friend)
[Audio] Speech started (chunk #25, 00:07:33.569)
[Audio] Echo skip: 6/25 pre-roll chunks trimmed
[Vision] Jagan
[Audio] Silence detected — waiting for end-of-turn...
[Vision] none
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Silence detected — waiting for end-of-turn...
[Privacy] _classify_privacy_level('from') → public (llm)
[Privacy] _classify_privacy_level('from') → public (cache)
[Privacy] _classify_privacy_level('from') → public (cache)
[BrainAgent] 00:07:38.241 Extracted 3 fact(s) (5760ms): Jagan.from='India', Jagan.from='Andhra Pradesh', Jagan.from='Tirupati'
[BrainAgent] Turn 9 → 3 fact(s) in 5784ms: Jagan.from='India', Jagan.from='Andhra Pradesh', Jagan.from='Tirupati'
[BrainAgent] 00:07:38.264 Triage: SKIP turn 10 — assistant turn (role=assistant, words=11, person_type=best_friend)
[Vision] Jagan
[Audio] Smart-Turn: turn complete (p=0.83, grace=0.48s)
[Audio] Turn end — 94 speech chunks, 0 lip extension(s)
[Vision] none
[STT] 00:07:40.929 (447ms) 'Do you know what all you know about Tirupathi? Can you tell me about the place?'
[Audio] Listening...
[Pipeline] State: LISTENING -> THINKING
[Vision] Jagan
[Voice] diarize: pyannote returned 1 segment(s)
[Voice] 00:07:41.585 Routing: current — jagan_992ed5 (score=0.846)
[Voice] diarize: pyannote returned 1 segment(s)
[STT] Jagan (voice=0.85): Do you know what all you know about Tirupathi? Can you tell me about the place?
[Pipeline] Turn start 00:07:41.651: Jagan — 'Do you know what all you know about Tirupathi? Can you tell ...'
[BrainAgent] Spawn (background): autocompact for Jagan
[BrainAgent] Spawn (background): emotion process_turn for Jagan
[Brain] Context: history=10 turns, memory=yes, emotion=no, room=no, scene=yes
[Pipeline] State: THINKING -> SPEAKING
[Voice] Refused accumulation for jagan_992ed5: no witness (face_conf=0.84, age=3.0s, voice_n=3, voice_conf=0.85, bootstrap=0)
[Brain] Context built: 11 messages, ~250 tokens
[Brain] Streaming meta-llama/Llama-3.3-70B-Instruct-Turbo... (~6,916 tokens)
[Vision] none
[Vision] Jagan
[Brain] 00:07:43.032 Tool: search_memory('Jagan', 'general')
[Privacy] 00:07:43.032 query_knowledge_for requester='jagan_992ed5' (owner-mode) entity='Jagan' → 3 row(s)
[Audio] TTS stream 00:07:44.078: 'I don't have much information about Tirupati itself, but I know it's where you're from, in Andhra Pradesh, India.'
[Vision] none
[Vision] Jagan
[Vision] none
[Audio] Playback complete — echo window reset (00:07:52.370)
[Pipeline] Turn addressed: Jagan (default; candidates=1)
[BrainAgent] Notify — waking agent loop
[Pipeline] Turn end 00:07:52.370: Jagan — 113 chars
[Pipeline] State: SPEAKING -> LISTENING
[Pipeline] Listening for Jagan...
[Audio] Listening...
[BrainAgent] 00:07:52.374 Triage: PASS turn 11 — processing (role=user, words=16, person_type=best_friend)
[BrainAgent] Extraction: no facts found in turn 11 (1406ms)
[BrainAgent] 00:07:53.781 Triage: SKIP turn 12 — assistant turn (role=assistant, words=19, person_type=best_friend)
[Vision] Person left frame: Jagan (conf=0.89)
[Audio] Speech started (chunk #101, 00:07:55.907)
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Silence detected — waiting for end-of-turn...
[Vision] Jagan
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Silence detected — waiting for end-of-turn...
[Vision] none
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Silence detected — waiting for end-of-turn...
[Vision] Active (LISTENING) — Jagan
[Vision] Jagan
[Audio] Silence detected — waiting for end-of-turn...
[Vision] none
[Vision] Jagan
[Audio] Smart-Turn: turn complete (p=0.81, grace=0.48s)
[Audio] Turn end — 183 speech chunks, 0 lip extension(s)
[STT] 00:08:08.402 (359ms) 'Do you know about Mumbai, Delhi, like any place? You have to describe any place and tell me. I just want to test how good you are in place describing.'
[Audio] Listening...
[Pipeline] State: LISTENING -> THINKING
[Voice] diarize: pyannote returned 2 segment(s)
[STT] 00:08:09.512 (303ms) 'Do you know about Mumbai, Delhi, like any place? You have to describe any place and tell me, I just want to test how good you are in place describing.'
[Voice] 00:08:09.513 Routing: current — jagan_992ed5 (score=0.799)
[Voice] diarize: pyannote returned 2 segment(s)
[STT] Jagan (voice=0.80): Do you know about Mumbai, Delhi, like any place? You have to describe any place and tell me. I just want to test how good you are in place describing.
[Pipeline] Turn start 00:08:09.678: Jagan — 'Do you know about Mumbai, Delhi, like any place? You have to...'
[BrainAgent] Spawn (background): autocompact for Jagan
[BrainAgent] Spawn (background): emotion process_turn for Jagan
[Brain] Context: history=12 turns, memory=yes, emotion=no, room=no, scene=yes
[Pipeline] State: THINKING -> SPEAKING
[Voice] Refused accumulation for jagan_992ed5: no witness (face_conf=0.85, age=2.6s, voice_n=3, voice_conf=0.80, bootstrap=0)
[Brain] Context built: 13 messages, ~332 tokens
[Brain] Streaming meta-llama/Llama-3.3-70B-Instruct-Turbo... (~6,998 tokens)
[Vision] none
[Brain] 00:08:11.485 search_web REJECTED — user turn contains no live-data marker — answer from knowledge: 'Mumbai description'
[Vision] Jagan
[Audio] TTS stream 00:08:13.254: 'Mumbai is a major city in India, known for its bustling streets, vibrant culture, and iconic landmarks like the Gateway of India.'
[Vision] none
[Vision] Jagan
[Vision] none
[Vision] Jagan
[Vision] none
[Vision] Jagan
[Vision] none
[Audio] Playback complete — echo window reset (00:08:23.826)
[Pipeline] Turn addressed: Jagan (default; candidates=1)
[BrainAgent] Notify — waking agent loop
[Pipeline] Turn end 00:08:23.828: Jagan — 129 chars
[Pipeline] State: SPEAKING -> LISTENING
[Pipeline] Listening for Jagan...
[Audio] Listening...
[BrainAgent] 00:08:23.832 Triage: PASS turn 13 — processing (role=user, words=30, person_type=best_friend)
[Vision] Jagan
[BrainAgent] Extraction: no facts found in turn 13 (1774ms)
[BrainAgent] 00:08:25.608 Triage: SKIP turn 14 — assistant turn (role=assistant, words=22, person_type=best_friend)
[Audio] Speech started (chunk #50, 00:08:25.724)
[Audio] Silence detected — waiting for end-of-turn...
[Vision] none
[Vision] Jagan
[Vision] none
[Audio] Silence detected — waiting for end-of-turn...
[Vision] Jagan
[Audio] Smart-Turn: turn complete (p=0.86, grace=0.48s)
[Audio] Turn end — 32 speech chunks, 0 lip extension(s)
[Vision] none
[Vision] Jagan
[STT] 00:08:28.500 (402ms) 'okay now what about delhi'
[Audio] Listening...
[Pipeline] State: LISTENING -> THINKING
[Voice] diarize: pyannote returned 1 segment(s)
[Voice] 00:08:29.184 Routing: current — jagan_992ed5 (score=0.708)
[Voice] diarize: pyannote returned 1 segment(s)
[STT] Jagan (voice=0.71): okay now what about delhi
[Pipeline] Turn start 00:08:29.245: Jagan — 'okay now what about delhi'
[BrainAgent] Spawn (background): autocompact for Jagan
[BrainAgent] Spawn (background): emotion process_turn for Jagan
[Brain] Context: history=14 turns, memory=yes, emotion=no, room=no, scene=yes
[Pipeline] State: THINKING -> SPEAKING
[Voice] Refused accumulation for jagan_992ed5: no witness (face_conf=0.85, age=0.8s, voice_n=3, voice_conf=0.71, bootstrap=0)
[Brain] Context built: 15 messages, ~383 tokens
[Brain] Streaming meta-llama/Llama-3.3-70B-Instruct-Turbo... (~7,049 tokens)
[Vision] none
[Vision] Active (SPEAKING) — Jagan
[Brain] 00:08:31.303 search_web REJECTED — user turn contains no live-data marker — answer from knowledge: 'Delhi information'
[Vision] Jagan
[Audio] TTS stream 00:08:33.677: 'Delhi is the capital city of India, steeped in history and home to many landmarks like the Red Fort and Qutub Minar.'
[Vision] none
[Vision] Jagan
[Vision] none
[Audio] Playback complete — echo window reset (00:08:43.066)
[Pipeline] Turn addressed: Jagan (default; candidates=1)
[BrainAgent] Notify — waking agent loop
[Pipeline] Turn end 00:08:43.067: Jagan — 116 chars
[Pipeline] State: SPEAKING -> LISTENING
[Pipeline] Listening for Jagan...
[Audio] Listening...
[BrainAgent] 00:08:43.080 Triage: PASS turn 15 — processing (role=user, words=5, person_type=best_friend)
[Vision] Jagan
[Audio] Speech started (chunk #19, 00:08:43.993)
[Audio] Echo skip: 5/19 pre-roll chunks trimmed
[Audio] Silence detected — waiting for end-of-turn...
[BrainAgent] Extraction: no facts found in turn 15 (1324ms)
[BrainAgent] 00:08:44.406 Triage: SKIP turn 16 — assistant turn (role=assistant, words=22, person_type=best_friend)
[Audio] Smart-Turn: turn complete (p=0.98, grace=0.19s)
[Audio] Turn end — 3 speech chunks, 0 lip extension(s)
[STT] 00:08:45.303 (317ms) 'Yes.'
[Audio] Listening...
[Vision] none
[Pipeline] State: LISTENING -> THINKING
[Voice] 00:08:45.935 Routing: current (short utterance 0.10s < 1.0s floor)
[Voice] diarize: pyannote returned 1 segment(s)
[STT] Jagan: Yes.
[Pipeline] Turn start 00:08:45.975: Jagan — 'Yes.'
[BrainAgent] Spawn (background): autocompact for Jagan
[BrainAgent] Spawn (background): emotion process_turn for Jagan
[Brain] Context: history=16 turns, memory=yes, emotion=yes, room=no, scene=yes
[Pipeline] State: THINKING -> SPEAKING
[Voice] Refused accumulation for jagan_992ed5: no witness (face_conf=0.89, age=2.4s, voice_n=3, voice_conf=0.71, bootstrap=0)
[Brain] Context built: 17 messages, ~425 tokens
[Brain] Streaming meta-llama/Llama-3.3-70B-Instruct-Turbo... (~7,132 tokens)
[Vision] Jagan
[Brain] 00:08:48.724 Tool: search_memory('Jagan', 'places')
[Privacy] 00:08:48.725 query_knowledge_for requester='jagan_992ed5' (owner-mode) entity='Jagan' → 3 row(s)
[Audio] TTS stream 00:08:50.315: 'I'm glad we could talk about some places in India, like Mumbai and Delhi.'
[Vision] none
[Vision] Jagan
[Vision] none
[Audio] Playback complete — echo window reset (00:08:55.853)
[Pipeline] Turn addressed: Jagan (default; candidates=1)
[BrainAgent] Notify — waking agent loop
[Pipeline] Turn end 00:08:55.854: Jagan — 73 chars
[Pipeline] State: SPEAKING -> LISTENING
[Pipeline] Listening for Jagan...
[Audio] Listening...
[BrainAgent] 00:08:55.859 Triage: PASS turn 17 — processing (role=user, words=1, person_type=best_friend)
[BrainAgent] Extraction: no facts found in turn 17 (1043ms)
[BrainAgent] 00:08:56.904 Triage: SKIP turn 18 — assistant turn (role=assistant, words=14, person_type=best_friend)
[Audio] Speech started (chunk #23, 00:08:56.931)
[Audio] Echo skip: 5/23 pre-roll chunks trimmed
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Silence detected — waiting for end-of-turn...
[Vision] Jagan
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Silence detected — waiting for end-of-turn...
[Vision] none
[Vision] Active (LISTENING) — Jagan
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Silence detected — waiting for end-of-turn...
[Vision] Jagan
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Silence detected — waiting for end-of-turn...
[Vision] none
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Silence detected — waiting for end-of-turn...
[Vision] Jagan
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Silence detected — waiting for end-of-turn...
[Vision] none
[Audio] Smart-Turn: turn complete (p=0.96, grace=0.19s)
[Audio] Turn end — 312 speech chunks, 0 lip extension(s)
[Vision] Jagan
[STT] 00:09:14.061 (511ms) "So now tell me the best place in the whole world like the best place in the month of May or month of April that anyone would I mean if anyone go there and they won't really want to come back I won't place something like that in the whole world."
[Audio] Listening...
[Pipeline] State: LISTENING -> THINKING
[Voice] diarize: pyannote returned 2 segment(s)
[STT] 00:09:15.375 (374ms) "So now tell me the best place in the whole world like the best place in the month of May or month of April that anyone would I mean if anyone go there and they won't really want to come back I won't place something like that in the whole world."
[Voice] 00:09:15.376 Routing: current — jagan_992ed5 (score=0.746)
[Voice] diarize: pyannote returned 2 segment(s)
[STT] Jagan (voice=0.75): So now tell me the best place in the whole world like the best place in the month of May or month of April that anyone would I mean if anyone go there and they won't really want to come back I won't place something like that in the whole world.
[Pipeline] Turn start 00:09:15.635: Jagan — 'So now tell me the best place in the whole world like the be...'
[BrainAgent] Spawn (background): autocompact for Jagan
[BrainAgent] Spawn (background): emotion process_turn for Jagan
[Brain] Context: history=18 turns, memory=yes, emotion=yes, room=no, scene=yes
[Pipeline] State: THINKING -> SPEAKING
[Voice] Refused accumulation for jagan_992ed5: no witness (face_conf=0.80, age=1.8s, voice_n=3, voice_conf=0.75, bootstrap=0)
[Brain] Context built: 19 messages, ~522 tokens
[Brain] Streaming meta-llama/Llama-3.3-70B-Instruct-Turbo... (~7,226 tokens)
[Vision] none
[Brain] 00:09:17.710 search_web REJECTED — user turn contains no live-data marker — answer from knowledge: 'best place to visit in May'
[Vision] Jagan
[Audio] TTS stream 00:09:19.333: 'Bali, Indonesia, is often considered a wonderful destination, with beautiful beaches and a lush green landscape, making it a great place to visit, especially in May when the weather is mild.'
[Vision] none
[Vision] Jagan
[Vision] none
[Vision] Jagan
[Vision] none
[Vision] Active (SPEAKING) — Jagan
[Vision] Jagan
[Audio] Playback complete — echo window reset (00:09:34.214)
[Pipeline] Turn addressed: Jagan (default; candidates=1)
[BrainAgent] Notify — waking agent loop
[Pipeline] Turn end 00:09:34.215: Jagan — 190 chars
[Pipeline] State: SPEAKING -> LISTENING
[Pipeline] Listening for Jagan...
[Audio] Listening...
[BrainAgent] 00:09:34.221 Triage: PASS turn 19 — processing (role=user, words=51, person_type=best_friend)
[BrainAgent] Extraction: no facts found in turn 19 (1246ms)
[BrainAgent] 00:09:35.468 Triage: SKIP turn 20 — assistant turn (role=assistant, words=31, person_type=best_friend)
[Vision] none
[Vision] Jagan
[Audio] Speech started (chunk #157, 00:09:39.511)
[Audio] Silence detected — waiting for end-of-turn...
[Audio] Silence detected — waiting for end-of-turn...
[Vision] none
[Audio] Smart-Turn: turn complete (p=0.97, grace=0.19s)
[Audio] Turn end — 69 speech chunks, 0 lip extension(s)
[Vision] Jagan
[STT] 00:09:44.372 (375ms) 'Hi Kara, can you tell me what is the escape velocity of earth?'
[Audio] Listening...
[Pipeline] State: LISTENING -> THINKING
[Voice] diarize: pyannote returned 2 segment(s)
[STT] 00:09:45.223 (228ms) 'Hi Kara, can you tell me what is the escape velocity of Earth?'
[Voice] 00:09:45.223 Routing: current — voice ambiguous, no other candidates in scene
[Voice] diarize: pyannote returned 2 segment(s)
[STT] Jagan: Hi Kara, can you tell me what is the escape velocity of earth?
[Pipeline] Turn start 00:09:45.284: Jagan — 'Hi Kara, can you tell me what is the escape velocity of eart...'
[BrainAgent] Spawn (background): autocompact for Jagan
[BrainAgent] Spawn (background): emotion process_turn for Jagan
[Brain] Context: history=20 turns, memory=yes, emotion=yes, room=no, scene=yes
[Pipeline] State: THINKING -> SPEAKING
[Voice] Refused accumulation for jagan_992ed5: no witness (face_conf=0.87, age=1.0s, voice_n=3, voice_conf=0.75, bootstrap=0)
[Brain] Context built: 21 messages, ~601 tokens
[Brain] Streaming meta-llama/Llama-3.3-70B-Instruct-Turbo... (~7,308 tokens)
[Vision] none
[Brain] 00:09:46.509 search_web REJECTED — user turn contains no live-data marker — answer from knowledge: 'escape velocity of earth'
[Audio] TTS stream 00:09:47.718: 'The escape velocity of Earth is about 11.2 kilometers per second.'
[Vision] Jagan
[Vision] none
[Audio] Playback complete — echo window reset (00:09:53.057)
[Pipeline] Turn addressed: Jagan (default; candidates=1)
[BrainAgent] Notify — waking agent loop
[Pipeline] Turn end 00:09:53.058: Jagan — 65 chars
[Pipeline] State: SPEAKING -> LISTENING
[Pipeline] Listening for Jagan...
[Audio] Listening...
[BrainAgent] 00:09:53.064 Triage: PASS turn 21 — processing (role=user, words=13, person_type=best_friend)
[Vision] Jagan
[BrainAgent] Extraction: no facts found in turn 21 (2357ms)
[BrainAgent] 00:09:55.422 Triage: SKIP turn 22 — assistant turn (role=assistant, words=11, person_type=best_friend)
[Audio] Speech started (chunk #74, 00:09:55.703)
[Audio] Silence detected — waiting for end-of-turn...
[Vision] none
[Audio] Smart-Turn: turn complete (p=0.98, grace=0.19s)
[Audio] Turn end — 3 speech chunks, 0 lip extension(s)
[STT] 00:09:57.508 (303ms) 'Thank you.'
[Audio] Listening...
[Pipeline] State: LISTENING -> THINKING
[Voice] diarize: pyannote returned 0 segment(s)
[Voice] 00:09:58.091 Routing: current (short utterance 0.10s < 1.0s floor)
[Voice] diarize: pyannote returned 0 segment(s)
[STT] Jagan: Thank you.
[Pipeline] Turn start 00:09:58.112: Jagan — 'Thank you.'
[BrainAgent] Spawn (background): autocompact for Jagan
[BrainAgent] Spawn (background): emotion process_turn for Jagan
[Brain] Context: history=22 turns, memory=yes, emotion=yes, room=no, scene=yes
[Pipeline] State: THINKING -> SPEAKING
[Voice] Refused accumulation for jagan_992ed5: no witness (face_conf=0.88, age=3.7s, voice_n=3, voice_conf=0.75, bootstrap=0)
[Brain] Context built: 23 messages, ~629 tokens
[Brain] Streaming meta-llama/Llama-3.3-70B-Instruct-Turbo... (~7,336 tokens)
[Vision] Jagan
[Brain] 00:10:00.550 search_web REJECTED — user turn contains no live-data marker — answer from knowledge: 'escape velocity of Earth'
[Dream] Force trigger — system has been busy, running dream during active session
[Dream] Starting consolidation cycle (idle=0.0min, force=True)
[Dream] Consolidation started — 1 person(s) in DB
[Dream] Consolidated — 0 pruned, 0 decayed, 3 stable
[Vision] none

[Pipeline] Ctrl+C received — shutting down gracefully...
[BrainAgent] Shutting down...
PS C:\Users\jagan\dog-ai\dog-ai> 