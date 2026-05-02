# KARAOS COMPLETE GUIDE
### Everything You Need to Know About Your AI Robot Dog System

**Written for:** The person who built this — but wants to understand every piece deeply enough to explain it to anyone.

**How to read this:** Every AI term is explained in plain English the first time it appears. If you see a word in **bold**, it is being defined right there. No assumed knowledge.

---

# TABLE OF CONTENTS

- [PART 1: THE BIG PICTURE](#part-1-the-big-picture)
- [PART 2: AI CONCEPTS EXPLAINED FROM SCRATCH](#part-2-ai-concepts-explained-from-scratch)
- [PART 3: THE RESEARCH PAPERS BEHIND KARAOS](#part-3-the-research-papers-behind-karaos)
- [PART 4: THE SYSTEM IN DETAIL](#part-4-the-system-in-detail)
- [PART 5: THE TEST SUITE EXPLAINED](#part-5-the-test-suite-explained)
- [PART 6: KEY DESIGN DECISIONS AND WHY](#part-6-key-design-decisions-and-why)
- [PART 7: HARD PROBLEMS SOLVED — THE STORIES](#part-7-hard-problems-solved--the-stories)
- [PART 8: GLOSSARY](#part-8-glossary)

---

# PART 1: THE BIG PICTURE

## 1.1 What Is KaraOS?

KaraOS is the brain of an AI robot dog. It is software — a collection of programs running together — that gives a robot dog the ability to:

- **See faces** through a camera and recognize who each person is
- **Hear voices** through a microphone and understand what people say
- **Remember** everything it has learned about each person across many days
- **Talk back** in a natural human voice
- **Learn** new things every conversation and update its understanding

Think of it as a very sophisticated social assistant that lives inside a robot dog body. Unlike a simple voice assistant (like Alexa or Siri), KaraOS does not just answer questions. It builds a relationship with each person it meets. It remembers your name, what you talked about last week, how you prefer to be spoken to, and even what mood you seem to be in.

The system runs on two computers:
- **Development machine:** A Windows 11 laptop (used for building and testing)
- **Production target:** A Jetson AGX Orin — a powerful NVIDIA computer designed for robots, about the size of a thick paperback book, with a built-in GPU (graphics processor) capable of running AI models

## 1.2 What Is a "Model"?

Before explaining the system, you need to understand one word that appears everywhere: **model**.

In AI, a **model** is a mathematical function that has been taught — through exposure to millions of examples — to recognize patterns. It is stored as a file full of numbers (called **weights**). When you feed it input (like a photo or audio recording), it produces output (like "this is Jagan's face" or "this sentence expresses sadness").

KaraOS uses about a dozen different models, each specializing in one task. A model that recognizes faces cannot hear voices. A model that detects emotion cannot translate speech to text. Each model is a specialist.

## 1.3 The Full Story: Jagan Walks In

Let us trace every single thing that happens when Jagan — the owner of the robot dog — walks into the room. This narrative will give you a mental map before we dive into details.

**00:00:000 — The camera wakes up**

The camera is capturing 30 frames per second (30 still images per second). The system does not analyze every frame with its full face-detection power — that would be too slow and expensive. Instead, it runs full face detection every 5th frame (about 6 times per second) and uses a clever mathematical tool called a **Kalman filter** to predict where each face is between those detections. Think of the Kalman filter as a physicist's best guess: "based on where this face was and how fast it was moving, it should be approximately here right now."

**00:00:167 — A face appears**

On the 5th frame, the full face detector (called **RetinaFace**, from the InsightFace library) runs. It finds a rectangle in the image that contains a face and also locates 5 **landmarks** — specific points on the face: left eye, right eye, nose tip, left mouth corner, right mouth corner.

**00:00:168 — Quality gates**

Before spending effort on recognition, the system runs four quality checks. These are called V1 through V4:

- **V1 (Size, blur, brightness):** Is the face large enough to recognize? Is it too blurry? Is the lighting reasonable? A tiny face at the edge of frame or a face in pitch darkness would fail this gate. Faces that fail V1 are ignored entirely.
- **V2 (Yaw angle):** Using the 5 landmarks, the system estimates how much the face is turned sideways. If the face is turned more than 60 degrees (a strong profile view), it is skipped. Recognition from a side view is unreliable.
- **V3 (Temporal buffer):** Instead of recognizing from a single frame, the system collects face images across 5 frames and **mean-pools** them (averages their numerical representations). This reduces the randomness from any single frame.
- **V4 (Adaptive threshold):** The system adjusts how strict it is based on quality. A blurry face needs to score higher to be recognized as a known person, because the uncertainty is higher.

**00:00:200 — Face embedding extraction**

The face image passes through a model called **AdaFace IR101**. This model was trained on millions of faces and learned to compress any face into a list of 512 numbers. These 512 numbers are called an **embedding** — they are a mathematical fingerprint of that face. Two images of Jagan's face will produce 512 numbers that are very similar to each other. An image of a stranger will produce very different numbers.

**00:00:201 — Anti-spoofing check**

Before trying to recognize the face, a separate model called **MiniFASNet** checks whether the face is real or a photograph/screen. This is called **liveness detection** or **anti-spoofing**. If someone held up a printed photo of Jagan to the camera, this check would catch it. Two small neural networks each vote on whether the face is real, and their probabilities are combined. A face must score above 0.5 to be considered live.

**00:00:202 — Recognition against the face database**

The 512-number embedding is compared against every face embedding stored in the database. The database uses a specialized search system called **FAISS** (Facebook AI Similarity Search) that can find the most similar stored embedding extremely quickly — even if there are thousands of stored faces. The comparison measure is called **cosine similarity** — it measures the angle between two sets of 512 numbers. A score of 1.0 means identical; a score of 0.0 means completely different. The threshold is 0.28 — anything above that is a potential match.

**00:00:203 — Identity confirmed: Jagan**

The database returns a match: `jagan_abc`, similarity score 0.74, name "Jagan". The system also applies **adaptive threshold** (V4) — because this particular frame had excellent quality, the threshold may be lower, making recognition easier. Jagan's identity is confirmed.

**00:00:204 — Session opens**

The pipeline opens a "session" for Jagan. A session is a Python dictionary (a collection of named values) that tracks everything about the current interaction: who this person is, when they arrived, how many turns of conversation have happened, their voice profile, their emotion history, and more.

**00:00:500 — Greeting**

The system looks up whether Jagan has been greeted recently (within the last 5 minutes, configurable via `GREET_COOLDOWN`). He has not been greeted today, so the system constructs a greeting. It checks whether there is any relevant memory to include — did Jagan mention something last session that deserves a follow-up? The **brain** (a large language model) generates a personalized greeting. The text goes to the **Text-to-Speech** (TTS) system, which converts it to audio using a model called **Kokoro**, and Jagan hears: "Welcome back, Jagan! How are you doing today?"

**00:02:000 — Jagan speaks**

Jagan says something. The microphone captures audio. A component called **VAD** (Voice Activity Detection) detects that speech has started. A second component called **Smart-Turn** (a small neural network) monitors whether Jagan has finished speaking — it looks for silences of 0.5 seconds or longer to determine turn end.

**00:02:003 — Speech to text**

The audio is passed to **Whisper** (a speech-to-text model from OpenAI, running locally). Whisper converts the audio waveform into text.

**00:02:004 — Voice identification**

Simultaneously, the audio is processed by **ECAPA-TDNN** (a voice recognition model from SpeechBrain). This model converts the audio into a 192-number voice embedding — a mathematical fingerprint of the speaker's voice. This embedding is compared against the stored voice profiles to confirm: yes, this sounds like Jagan. This is a safety check — what if someone grabbed the robot dog and was talking to it while Jagan's face happened to be visible nearby?

**00:02:005 — Speaker routing**

The system runs a cascade of 22 rules (called the **reconciler**) to determine: who is actually speaking right now? The cascade considers: whose face is visible, what the voice ID says, whether the voice score is high enough, how long since the last confirmed sighting, and several edge cases. In this simple scenario, the answer is obvious: Jagan.

**00:02:006 — Intent classification**

Before sending Jagan's words to the main AI brain, a smaller, faster classifier runs to determine what kind of message this is. Did Jagan say his own name (suggesting a rename request)? Is he asking for live data that requires a web search? Is he asking the robot to shut down? The classifier returns a label like `casual_conversation` or `live_data_query` and a confidence score.

**00:02:007 — Brain processes the message**

Jagan's message, along with the full conversation history, the system prompt (instructions to the AI), the current scene description (who is visible on camera), memory context (relevant things from past sessions), and other context is sent to the AI brain: **Llama-3.3-70B-Instruct-Turbo** running on Together.ai's servers. This is the system's main intelligence — a 70-billion parameter language model trained on vast amounts of human text.

The brain generates a response. If the response requires a tool (like searching the web, or updating a name), the tool is called. The response streams back word by word.

**00:02:008 — Knowledge extraction (background)**

While the brain is responding, the system quietly runs **knowledge extraction** in the background. A specialized model reads Jagan's message and extracts structured facts: "Jagan mentioned he is tired." "Jagan said his name is Jagan." These facts are stored in the knowledge database (**brain.db**) under Jagan's identity, classified by privacy tier (is this personal information? household information? public?).

**00:02:010 — Response spoken aloud**

The brain's response is converted to speech and played through speakers. The text is cleaned first — markdown formatting, bold asterisks, code backticks, em dashes, and list markers are all stripped out so the text sounds natural when spoken.

**00:02:011 — Memory and graph updates (background)**

After the response, multiple agents run in background:
- The **emotion agent** updates Jagan's emotional state based on the conversation
- The **graph agent** adds relationships to the knowledge graph (did Jagan mention someone new?)
- The **contradiction agent** checks if any new facts contradict stored facts
- The **prompt preference agent** learns how Jagan prefers to be spoken to (brief? detailed? formal?)

**Later — Jagan leaves**

When Jagan's face disappears from frame, the system waits for a **grace period** of 10 seconds (in case he just ducked out of camera view). If he doesn't return, the session closes. A background agent synthesizes the conversation for long-term memory storage.

This is KaraOS. Every single step described above has its own specialized code, its own tests, and its own design decisions — all explained in the sections below.

---

# PART 2: AI CONCEPTS EXPLAINED FROM SCRATCH

## 2.1 Neural Networks: Teaching by Example

A **neural network** is the core building block of modern AI. Understanding it requires understanding how humans learn versus how computers traditionally work.

A traditional computer program follows explicit rules. To sort numbers: "compare the first two, swap if the second is smaller, repeat." The rules are written by a programmer.

A neural network learns rules from examples, not from explicit instructions. Instead of programming "a face has two eyes, a nose, and a mouth in approximately these positions," you show the network millions of labeled photos ("this is a face," "this is not a face") and it discovers the rules on its own.

**How it actually works:**

Imagine a network of artificial neurons arranged in layers. Each neuron is just a number. The first layer receives the raw input (like pixels in an image). Each neuron in the next layer computes a weighted sum of all neurons in the previous layer, then applies a simple nonlinear function (called an **activation function**) that decides how much to "fire." The final layer produces the output.

The "learning" happens during **training**. You feed the network a labeled example. It makes a prediction. You measure how wrong that prediction was (the **loss**). Then, using a mathematical technique called **backpropagation** and an optimization algorithm called **gradient descent**, the weights throughout the network are adjusted slightly in the direction that reduces the error. Repeat this millions of times on millions of examples, and the weights gradually settle into values that make good predictions.

The weights — those adjusted numbers — are what gets saved to disk when you "save a model." The file is large (a model like Llama-3.3-70B has 70 billion weights) because it encodes everything the network learned from its training data.

**Why "deep" learning?**

Early neural networks had only a few layers. Modern networks have hundreds of layers — this "depth" is why the field is called **deep learning**. Each additional layer learns increasingly abstract patterns. The first layer of an image recognition network learns edges and corners. The middle layers learn shapes and textures. The final layers learn high-level concepts like "face" or "dog."

## 2.2 Embeddings: Turning Words and Faces into Numbers

Every AI model ultimately works with numbers. Text, audio, and images all need to be converted into numerical representations before any computation can happen. The most important such representation is called an **embedding**.

**The core idea:**

An embedding is a list of numbers (a **vector**) that represents some object — a face, a sentence, a word, a sound — in a way that captures meaning. The magical property of good embeddings is: similar things have similar numbers.

For faces: two photos of Jagan produce vectors that are close to each other in 512-dimensional space. A photo of a stranger produces a vector far away from Jagan's.

For words: the embedding of "king" minus the embedding of "man" plus the embedding of "woman" produces a vector very close to the embedding of "queen." This is the famous Word2Vec example — arithmetic on meaning.

For sentences: "I love dogs" and "Dogs are my favorite animals" produce similar embeddings. "The stock market fell today" produces a very different embedding.

**Why 512 dimensions, or 192, or 1024?**

The number of dimensions (the length of the vector) is a design choice made during model training. More dimensions means the model can capture more nuance, but requires more storage and computation. The face model (AdaFace) uses 512 dimensions. The voice model (ECAPA-TDNN) uses 192. The semantic text model (multilingual-e5) uses 1024.

**L2 normalization:**

Before most comparisons, embeddings are "normalized" — scaled so the vector has length exactly 1.0. This is called **L2 normalization** (named after the L2 mathematical norm). After normalization, the similarity between two embeddings is captured entirely by their angle — not their magnitude. This makes comparisons consistent regardless of how "confident" or "loud" a given embedding is.

## 2.3 Cosine Similarity: Measuring the Angle Between Vectors

Once you have embeddings (lists of numbers representing faces or voices or text), you need a way to ask: "how similar are these two things?" The standard answer is **cosine similarity**.

**The intuition:**

Imagine each embedding as an arrow pointing from the origin (0,0,...,0) out into 512-dimensional space. Two very similar things point in nearly the same direction. Two very different things point in very different directions.

Cosine similarity measures the cosine of the angle between two arrows. Cos(0°) = 1.0 (same direction, identical). Cos(90°) = 0.0 (perpendicular, unrelated). Cos(180°) = -1.0 (opposite directions).

**The formula:**

For two vectors A and B, cosine similarity = (A · B) / (|A| × |B|)

Where A · B is the **dot product** (multiply corresponding elements, add them all up), and |A| is the vector's length.

After L2 normalization, |A| = |B| = 1.0, so the formula simplifies to just: A · B

This is why FAISS uses `IndexFlatIP` (Inner Product) — after normalization, inner product equals cosine similarity.

**In KaraOS:** The face recognition threshold is 0.28. A cosine similarity of 0.28 or higher means "same person." The voice switch threshold for mature profiles is 0.40. These numbers were calibrated empirically — tested with real data until false matches and false rejections were minimized.

## 2.4 Transformers: The Architecture Behind Modern AI

The **transformer** is the architectural breakthrough that made modern language AI possible. It was introduced in the 2017 paper "Attention Is All You Need" by Vaswani et al. at Google.

**Before transformers:**

Previous sequence models (like RNNs and LSTMs) processed text left to right, one word at a time. By the time they reached word 100 in a long document, they had often "forgotten" what was in word 1. They struggled with long-range dependencies.

**The attention mechanism:**

The key innovation in transformers is **self-attention**. For every word in a sentence, attention computes a score against every other word: "how relevant is this other word to understanding the current word?" These scores determine how much each word should "pay attention to" every other word when computing its representation.

For example, in "The animal didn't cross the street because it was too tired" — when encoding "it," attention learns to pay strong attention to "animal" (the referent), not "street."

**Why transformers scale:**

Unlike RNNs, transformers process all words simultaneously (not sequentially). This allows much more efficient use of parallel computing hardware (GPUs). Combined with the insight that simply making models bigger and training them on more data keeps improving performance, the transformer architecture led to GPT, BERT, Llama, and every other major modern language model.

**In KaraOS:** The main brain (Llama-3.3-70B) is a transformer. Whisper (speech recognition) is a transformer. The emotion classifier is a fine-tuned transformer. The text embedding model (multilingual-e5) is a transformer.

## 2.5 Fine-Tuning: Specializing a General Model

**Pre-training** is the expensive step: training a large model on enormous amounts of general data. GPT-4 was pre-trained on hundreds of billions of tokens. This costs millions of dollars and takes months.

**Fine-tuning** is the inexpensive step: taking a pre-trained model and training it for a short additional time on a smaller, task-specific dataset. The model's general knowledge is preserved, but its behavior is adjusted for the specific task.

**Example:** The emotion classifier in KaraOS is based on `distilroberta-base` — a small, fast transformer pre-trained on general English text. It was then **fine-tuned** by a researcher named j-hartmann on a dataset of emotional conversations, teaching it to classify text into 7 emotions: joy, sadness, anger, fear, disgust, surprise, neutral. KaraOS uses this fine-tuned model without any additional training.

**In-context learning vs fine-tuning:**

There is another technique that looks like fine-tuning but is not: giving examples in the prompt (the system instructions). When KaraOS's intent classifier sees examples of "I want to rename you Kara" being classified as `assign_system_name`, it is using **in-context learning** (the transformer learns from the examples in its context window for that specific inference call). No weights are changed. This is much cheaper but less reliable than true fine-tuning.

## 2.6 FAISS: Finding the Most Similar Face in Milliseconds

**The problem:** Jagan's face produces a 512-number vector. The database contains embeddings for 10 people, each with up to 50 stored embeddings (500 vectors total). To find who Jagan is, you need to find the stored vector most similar to his current embedding.

This is called a **nearest neighbor search** — find the closest point in a database to a query point.

**The naive approach:** Compare the query vector against every stored vector using cosine similarity. For 500 vectors of 512 numbers, this requires 500 × 512 = 256,000 multiplications and additions. That is fast for 500 vectors. But if the database had 1 million vectors, it would require 512 million operations — potentially too slow for real-time recognition.

**FAISS (Facebook AI Similarity Search):** FAISS is an open-source library from Meta (Facebook) that makes nearest-neighbor search fast. For KaraOS's database size (a few thousand embeddings), FAISS uses `IndexFlatIP` — "flat" meaning it stores all vectors directly without compression, "IP" meaning Inner Product (cosine similarity after normalization). This gives **exact** results (not approximations) at high speed.

For much larger databases (millions of vectors), FAISS has approximate methods that trade a small amount of accuracy for dramatically faster search. KaraOS doesn't need these — a few hundred face embeddings is trivially small.

**The critical bug fix (Session 1):** Early in development, deleting a person from the database required rebuilding the entire FAISS index from scratch. The bug was that FAISS's "remove" operation was not working correctly for this index type. The fix: always call `_rebuild_faiss()` after any deletion, which reconstructs the index from the remaining SQLite records. This is now a coding standard: "delete_person() always rebuilds FAISS — never call DELETE directly."

## 2.7 The Kalman Filter: Predicting Where a Face Will Be

Detecting faces is expensive — it requires running a neural network on the image, taking about 30 milliseconds. Running it on every frame at 30fps would consume almost all available computation.

The solution is to run face detection only every 5th frame and use a **Kalman filter** to predict face positions in between detections.

**What is a Kalman filter?**

A Kalman filter is an algorithm from control theory (developed by Rudolf Kalman in 1960) that maintains a best estimate of a system's state and updates that estimate as new measurements arrive. It is "optimal" in the mathematical sense — it minimizes expected estimation error given the noise characteristics of both the motion model and the measurements.

For face tracking, the "state" is: x-position, y-position, width, height, and their velocities. Each frame, the filter:
1. **Predicts:** Based on current velocity, where should this face be now?
2. **Updates:** If we have a new detection, correct the prediction toward the measurement

The SORT (Simple Online and Realtime Tracking) algorithm used by KaraOS wraps a Kalman filter for each tracked face and uses the **Hungarian algorithm** to optimally assign new detections to existing tracked faces.

**Why the Hungarian algorithm?**

When multiple faces are visible and multiple detections arrive, you need to determine which detection corresponds to which tracked face. This is an **assignment problem** — a classic combinatorial optimization problem. The Hungarian algorithm (also called the Kuhn-Munkres algorithm) finds the optimal assignment in polynomial time. "Optimal" here means the assignment that maximizes total similarity between predictions and detections.

Before Session 24's fix (Bug B6), KaraOS used a greedy assignment that could match a detection to the wrong track. The Hungarian algorithm eliminated this class of error.

## 2.8 Speaker Diarization: Who Said What?

**Diarization** comes from the French "journal" and means "who speaks when." It is the problem of segmenting an audio recording by speaker identity.

Simple speech recognition converts audio to text. Diarization additionally labels each segment with a speaker identifier — "Speaker A said X, then Speaker B said Y."

**Why this is hard:**

In real conversations, people interrupt, overlap, mumble, change distance from the microphone, and have vocal characteristics that vary with emotion and fatigue. Separating them requires understanding the acoustic structure of speech at a very fine level.

**pyannote.audio:**

KaraOS uses `pyannote.audio 3.3.2`, a deep learning-based diarization system. Pyannote was trained on large datasets of multi-speaker audio and learned to segment by speaker using **speaker embeddings** (voice fingerprints extracted from short audio segments). It returns segments like: "0.0-1.3s: SPEAKER_00, 1.3-2.7s: SPEAKER_01, 2.7-3.9s: SPEAKER_00."

**Why pyannote required 7 compatibility patches:**

The version pinned (3.3.2) was written for an older version of PyTorch and torchaudio. By the time KaraOS was built, torchaudio had removed three APIs that pyannote depended on (`set_audio_backend`, `list_audio_backends`, `AudioMetaData`). The fix is a script (`tests/patch_pyannote_io.py`) that surgically edits pyannote's source files to use the replacement APIs. This must be re-run after any reinstallation of pyannote.

## 2.9 Voice Activity Detection: Knowing When Someone Is Speaking

**Voice Activity Detection (VAD)** is the problem of detecting whether audio contains speech or noise/silence. It sounds simple but is important — without VAD, the speech recognition model would run on silence, wasting computation and potentially hallucinating words.

**RMS threshold VAD:**

The simplest approach is RMS (Root Mean Square) thresholding. Measure the "loudness" of a short audio chunk. If loudness exceeds a threshold, declare it speech. This is fast and works in quiet environments. KaraOS uses this by default on the development laptop (`VAD_SWITCH = False` in config means RMS is active).

**Silero VAD:**

A more sophisticated approach, planned for the production Jetson, uses a small neural network (Silero VAD) trained specifically to distinguish speech from non-speech sounds. It handles background noise, music, and other sounds that might confuse RMS thresholding.

**Smart-Turn:**

KaraOS also uses a second VAD-like system for a different purpose: detecting when a person has finished their turn. This is the `Smart-Turn` model — an ~8MB ONNX neural network that monitors audio after speech starts and predicts when the speaker has truly finished (vs. paused mid-sentence). It triggers at 0.5 seconds of silence with 80% confidence. Without it, the system would either cut off speakers who pause to think, or wait too long after they finish.

## 2.10 Property Graphs: Storing Relationships

A **property graph** is a way to store information about things and their relationships. It consists of:
- **Nodes:** Things (people, concepts, places)
- **Edges:** Relationships between things ("Jagan KNOWS Lexi," "Lexi STUDIES_AT university")
- **Properties:** Attributes on nodes and edges ("name: Jagan," "confidence: 0.9")

A relational database (like SQLite) is excellent for storing rows of facts. But relationships between entities — especially multi-hop relationships like "who are friends-of-friends?" — require many joins and become complex. A property graph stores relationships as first-class data, making traversals natural.

**Kuzu:**

KaraOS uses **Kuzu**, an embedded property graph database. "Embedded" means it runs inside the same process as KaraOS, like SQLite — no separate server required.

**Example use:**

When Jagan says "Lexi is my classmate," the system stores:
- A `Person` node for Lexi (if not already present)
- A `RELATES_TO` edge from Jagan to Lexi with property `relationship: classmate`

Later, if someone asks "what do you know about Jagan's connections?", the system can traverse these edges to surface relevant relationships.

## 2.11 Semantic Search: Finding Information by Meaning

**Keyword search** finds documents containing specific words. Searching for "feels sad" will not find "expressing melancholy."

**Semantic search** finds documents by meaning, regardless of exact words. It works by embedding the query and all documents into the same vector space, then finding documents whose embeddings are closest to the query embedding.

**How KaraOS uses it:**

When the brain wants to recall relevant memories about Jagan (to use as context for the current conversation), it doesn't search for exact phrases Jagan said. It embeds the current conversation topic and searches for stored facts that are semantically similar — even if different words were used.

The embedding model is `intfloat/multilingual-e5-large-instruct`, producing 1024-dimensional embeddings. These are stored as BLOBs (binary data) in SQLite and compared in-memory during search.

**The privacy layer:**

KaraOS adds a privacy filter on top of semantic search. Before returning semantically similar facts, the system checks whether the requester is allowed to see them. A stranger cannot see Jagan's personal facts even if their query semantically matches. This is the `_visibility_clause` function — a SQL predicate that enforces four privacy tiers (public, personal, household, system_only).

## 2.12 The Wilson Lower Bound: Cautious Confidence Estimation

When the graph-based intent classifier needs to report how confident it is about a label, it uses the **Wilson score interval lower bound** for confidence estimation.

**The problem with naive averaging:**

If a scenario was confirmed 3 times and rejected 0 times, a naive estimate would say "100% confidence." But with only 3 data points, that is overconfident. The next confirmation could be a rejection.

**The Wilson bound:**

The Wilson score interval is a statistical technique that says: "given N observations and k successes, what is the 95% confidence lower bound on the true success rate?" It is more conservative than naive averaging — with 3/3 confirmations, it might say 60% rather than 100%. With 100/100 confirmations, it says something close to 100%.

**Why it matters in KaraOS:**

The graph classifier builds confidence about each intent label based on outcome feedback from past sessions. Using the Wilson bound prevents new or rarely-tested scenarios from being over-trusted. A new scenario with 2 confirmations and no rejections will have a lower Wilson bound than an established scenario confirmed 50 times — correctly so, because we have less evidence about the new one.

---

# PART 3: THE RESEARCH PAPERS BEHIND KARAOS

## 3.1 RetinaFace: Precise Face Detection

**Paper:** "RetinaFace: Single-stage Dense Face Localisation in the Wild" (Deng et al., 2019, CVPR 2020)

**What the paper discovered:**

Previous face detectors found face bounding boxes but did not localize facial landmarks (eyes, nose, mouth corners) accurately, especially for small or partially occluded faces. RetinaFace showed that simultaneously predicting the face box, 5 facial landmarks, and a 3D face shape in a single network pass (single-stage) achieved state-of-the-art performance while remaining fast.

The key insight was **multi-task learning**: training the network to solve multiple related tasks simultaneously. The shared feature representations learned for one task help all others — landmark localization helps bounding box accuracy, and vice versa.

**Why KaraOS uses it:**

The 5 landmarks (both eyes, nose tip, both mouth corners) are used for two purposes:
1. Aligning the face image (rotating and scaling it to a canonical pose) before embedding extraction — this improves recognition accuracy
2. Estimating the **yaw angle** (how much the face is turned left or right) for the V2 quality gate

KaraOS accesses RetinaFace through the InsightFace library's `buffalo_l` model pack, which bundles RetinaFace with the AdaFace embedding model.

## 3.2 AdaFace: Adaptive Face Recognition

**Paper:** "AdaFace: Quality Adaptive Margin for Face Recognition" (Kim et al., 2022, CVPR 2022)

**What the paper discovered:**

Face recognition models have to handle both high-quality images (studio photos, frontal views) and low-quality images (surveillance cameras, partial occlusion, poor lighting). Previous approaches used a fixed recognition margin — the same strictness regardless of image quality.

AdaFace proposed **adaptive margin** — harder (stricter) margin for high-quality images, softer margin for low-quality images. The margin adapts based on the estimated quality of the face image. This improved performance across all quality levels, especially on low-quality surveillance images.

The model uses an IR-101 backbone (101-layer ResNet with improved residual connections for images) and was trained on faces with varying quality levels.

**Why KaraOS uses it:**

AdaFace produces 512-dimensional face embeddings that are resilient to varying lighting, pose, and image quality. The `IR101` (101-layer) variant is used — deeper than smaller variants, giving better accuracy at the cost of slightly more computation. KaraOS's V4 quality gate directly parallels AdaFace's philosophy: the recognition threshold adapts based on the estimated quality of the incoming face image.

The model runs as an ONNX file (an optimized format for inference), which allows it to run efficiently on both CPU and GPU.

## 3.3 SORT: Simple Online and Realtime Tracking

**Paper:** "Simple Online and Realtime Tracking" (Bewley et al., 2016, ICIP 2016)

**What the paper discovered:**

Multi-object tracking is the problem of following multiple objects across video frames as they move. The paper showed that a surprisingly simple approach — **Kalman filter** for motion prediction + **Hungarian algorithm** for assignment + **IoU (Intersection over Union)** for similarity — achieved excellent real-time tracking performance despite being much simpler than previous methods.

The key insight was that the bottleneck in tracking performance was detection quality, not tracking algorithm sophistication. Given good detections, the simple SORT pipeline was nearly as good as much more complex methods.

**Why KaraOS uses it:**

SORT allows KaraOS to track multiple faces simultaneously across video frames, even when detection runs only every 5th frame. Each tracked face gets a `track_id` — a stable identifier that persists as long as the face is continuously visible. This `track_id` is essential for:
- Associating voices with faces (the voice of the person with track_id 3 is being stored in a per-track buffer)
- Accumulating multi-frame embeddings (V3 temporal buffer, keyed by track_id)
- Tracking which stranger is which when multiple unknown people are visible

Session 24 replaced SORT's default greedy assignment with the proper Hungarian algorithm, eliminating a bug class where the system could mistakenly switch which track corresponded to which face.

## 3.4 ECAPA-TDNN: State-of-the-Art Speaker Recognition

**Paper:** "ECAPA-TDNN: Emphasized Channel Attention, Propagation and Aggregation in TDNN Based Speaker Verification" (Desplanques et al., 2020, Interspeech 2020)

**What the paper discovered:**

Speaker verification (confirming "is this person who they claim to be?") and speaker identification (determining "who is this person?") both rely on extracting a **speaker embedding** from audio. Previous work used TDNN (Time Delay Neural Network) architectures. ECAPA-TDNN improved on these with:

1. **Channel attention:** Not all frequency bands are equally informative for recognizing a speaker. ECAPA learns to weight frequency channels differently.
2. **Multi-scale aggregation:** Combining information across different time scales — short-term phonetic content and longer-term speaking style patterns.
3. **Squeeze-and-excitation blocks:** A mechanism for the network to dynamically recalibrate feature importance.

**Why KaraOS uses it:**

ECAPA-TDNN produces 192-dimensional voice embeddings that capture a person's unique vocal characteristics. These are stored in the `voice_embeddings` SQLite table and compared against new recordings to identify speakers. The model is accessed through the SpeechBrain library and runs on GPU.

The system requires 5 samples (`N_INITIAL_VOICE`) before a speaker's profile is considered "mature." New or thin profiles use a higher matching threshold (0.55 vs 0.40 for mature profiles) because there is less evidence.

## 3.5 Whisper: Reliable Speech-to-Text

**Paper:** "Robust Speech Recognition via Large-Scale Weak Supervision" (Radford et al., 2022, OpenAI)

**What the paper discovered:**

Previous speech recognition systems were trained on expensive, carefully labeled datasets. Whisper was trained on 680,000 hours of audio from the internet — much of it automatically aligned (the audio and transcript were paired by downloading subtitles alongside videos). This "weak supervision" was far cheaper to produce but required the model to be robust to noisy, diverse audio.

The result was a model that generalized much better than previous approaches to accented speech, background noise, different speaking styles, and technical vocabulary. It also naturally supported multiple languages.

**Why KaraOS uses it:**

KaraOS uses `faster-whisper large-v3-turbo` — a version of Whisper optimized for speed using **CTranslate2** (an inference engine that uses quantization and other tricks to run models faster without significant accuracy loss). It runs on GPU with float16 precision and is constrained to English (`language="en"` always, because the entire system is English-only).

One important detail: Whisper is known to "hallucinate" text on pure silence or noise. KaraOS filters these hallucinations:
- A filter for character runs (16+ consecutive same characters, like "Mmmmm...")
- A filter for word repetitions (the same word repeated many times)
- These filters run before the text reaches the brain

## 3.6 MiniFASNet: Liveness Detection Against Spoofing

**Paper:** "Searching Central Difference Convolutional Networks for Face Anti-Spoofing" (Yu et al., 2020, CVPR 2020)

**What the paper discovered:**

Face anti-spoofing (liveness detection) tries to distinguish real faces from attacks — printed photos, video replays on screens, 3D masks. Previous methods used hand-crafted features (texture, reflectance). This paper proposed using **neural architecture search** to automatically find the best convolutional network for anti-spoofing, discovering architectures that capture fine-grained texture differences between real skin and printed/displayed surfaces.

The MiniFASNet models (V1 and V2) are small, fast variants from the minivision-ai implementation that are suitable for real-time use on edge devices.

**Why KaraOS uses it:**

Without anti-spoofing, someone could hold up a printed photo of Jagan to the camera and get recognized as him — a serious security flaw. MiniFASNet is an ensemble of two models (V1 and V2) whose softmax probabilities are averaged. Class 1 (argmax=1) = live face. A probability above 0.5 for class 1 passes the liveness check.

**The critical implementation detail discovered in Session 59:**

The upstream minivision-ai implementation does NOT divide input pixel values by 255. The model was trained on raw [0, 255] float values. When the first implementation applied `.div(255.0)` to normalize pixels to [0, 1], every real face was classified as a replay attack with 95%+ confidence. The fix was a one-line removal. This is documented as a cautionary tale: always understand the exact preprocessing a model expects.

## 3.7 Kokoro: Natural Text-to-Speech

**Kokoro** is an ONNX-based text-to-speech model. The voice `af_heart` is used as the primary voice — it produces natural, expressive English speech.

TTS is the opposite of STT (speech-to-text). Given text, it produces a waveform of audio that sounds like a human speaking. Modern neural TTS (unlike the robotic voice synthesizers of the 1990s) uses deep learning to capture the natural prosody, rhythm, and expressiveness of human speech.

**Why a fallback exists (Piper):**

Kokoro requires more computation. If Kokoro fails to initialize (e.g., on a system with limited resources), the system falls back to **Piper** — a lighter TTS engine using `en_US-lessac-medium.onnx`. Piper is less natural-sounding but reliable.

**Text cleaning before TTS:**

Before any text reaches Kokoro or Piper, it goes through `_clean_for_tts()`. This function strips:
- Markdown formatting: `**bold**`, `*italic*`, `` `code` ``, `# headers`
- List markers: `- `, `• `, `1. `
- Em dashes: `—`
- Markdown links: `[text](url)` → `text`
- Meta-commentary patterns: sentences like "No function call is needed" that are AI internal reasoning accidentally verbalized

Without this cleaning, the AI might say "asterisk asterisk important asterisk asterisk" instead of just "important."

## 3.8 DistilRoBERTa: Emotion Classification

**Paper:** "DistilBERT, a distilled version of BERT" (Sanh et al., 2019) + j-hartmann fine-tuning for emotions

**What the research discovered:**

**BERT** (Bidirectional Encoder Representations from Transformers, Google 2018) was a major breakthrough in NLP — a transformer trained to understand language by predicting masked words and next sentences. It captured deep contextual meaning.

**DistilBERT** applied **knowledge distillation** to BERT: train a smaller "student" model to mimic a larger "teacher" model. The student is 40% smaller and 60% faster while retaining 97% of BERT's performance.

**RoBERTa** (Robustly Optimized BERT, Facebook 2019) improved BERT's training recipe — more data, longer training, no next-sentence prediction task.

**DistilRoBERTa** combines both: a distilled version of RoBERTa.

**j-hartmann's emotion fine-tuning:** A researcher named Jochen Hartmann fine-tuned DistilRoBERTa on emotion-labeled conversation datasets, producing a model that classifies any sentence into one of 7 emotions: joy, sadness, anger, fear, disgust, surprise, neutral.

**Why KaraOS uses it:**

KaraOS maintains a per-person emotional state tracker. Each turn, the emotion model classifies what the person said. A rolling 5-turn window determines the dominant emotion. If 2+ consecutive turns are non-neutral, an emotional fact is stored ("Jagan has been expressing joy").

The model runs on CPU (not GPU) to avoid contention with the more time-sensitive face and voice models.

## 3.9 Multilingual-E5: Semantic Text Embeddings

**Paper:** "Text Embeddings by Weakly-Supervised Contrastive Pre-training" (Wang et al., 2022, Microsoft Research)

**What the research discovered:**

E5 (EmbEddings from bidirEctional Encoder rEpresentations) is trained using **contrastive learning** — given pairs of semantically related texts, train the model to produce similar embeddings for related pairs and dissimilar embeddings for unrelated pairs. The "weak supervision" comes from naturally occurring text pairs (question-answer pairs from forums, title-body pairs from news articles) rather than expensive human annotation.

The `multilingual` variant extends this to 100 languages. The `large` variant uses a larger model for better quality. The `instruct` variant prepends task-specific instructions (like "query: " or "passage: ") to distinguish different use cases.

**Why KaraOS uses it:**

All semantic memory search in KaraOS uses this model to embed both stored facts and queries. A 1024-dimensional embedding captures the meaning of any sentence well enough for retrieval. The model runs via Together.ai's API (not locally) with a 2-retry exponential backoff on transient failures.

## 3.10 Cornell Movie-Dialogs, DailyDialog, EmpatheticDialogues: Training Data

These are publicly available conversation datasets used to build the seed data for KaraOS's graph-based intent classifier.

**Cornell Movie-Dialogs Corpus** (Danescu-Niculescu-Mizil & Lee, 2011): 220,579 conversational exchanges from 617 movies, extracted from IMDb subtitles. Natural, informal dialogue with diverse vocabulary and styles.

**DailyDialog** (Li et al., 2017): 13,118 daily-life conversations covering topics like ordinary life, school, health, attitudes and emotions. Written to reflect typical human-to-human dialogue patterns.

**EmpatheticDialogues** (Rashkin et al., 2019, Facebook AI Research): 24,850 conversations where one person describes a situation evoking a specific emotion and another person responds empathetically. Designed to train models for emotional understanding.

**How KaraOS uses them:**

These corpora provide diverse, realistic conversation examples. For each example, KaraOS:
1. Strips all person names and place names (using spacy NER) to prevent overfitting to specific names
2. Runs the conversation through the 70B LLM to classify it with an intent label
3. Embeds it with E5
4. Stores it in the classifier scenarios database

The result is ~1,500-1,700 scenarios that teach the graph classifier what different kinds of utterances look like — before it ever sees a single real KaraOS conversation.

**Why Friends and AMI corpora are deliberately excluded:**

The Friends TV show corpus and AMI meeting corpus are used in published benchmark papers for evaluating conversational AI systems. Including them in training data would make KaraOS's performance look artificially good on those benchmarks (a form of "data leakage"). They are held out to preserve the integrity of future evaluation.

## 3.11 Llama 3.3: The Main Brain

**Model:** `meta-llama/Llama-3.3-70B-Instruct-Turbo` (Meta AI, 2024)

**What it is:**

Llama 3.3 is Meta's third generation of Large Language Models (LLMs). The 70B refers to 70 billion parameters (weights). "Instruct" means it was fine-tuned to follow instructions (as opposed to just continuing text). "Turbo" indicates a speed-optimized version.

At 70 billion parameters, this is a very large model — large enough to understand nuanced instructions, engage in complex reasoning, maintain conversation context, and call tools appropriately.

**Why this specific model:**

KaraOS previously used Google Gemini, then migrated to Together.ai's Llama hosting (Sessions 4-5). The choice was made for reliability, cost, and privacy (conversations do not go through Google's or OpenAI's infrastructure).

**Fallback:** Ollama running `qwen2.5:7b` locally is the fallback when Together.ai is unreachable. Qwen is smaller and less capable but works offline. It receives no tools and no conversation history — it operates in stateless Q&A mode.

---

# PART 4: THE SYSTEM IN DETAIL

## 4.1 The Camera Pipeline: From Pixels to Identity

**File:** `core/vision.py`

The camera pipeline runs in a background loop called `_background_vision_loop`. Here is the complete flow:

1. **Frame capture:** The `Camera` class captures frames. On Windows, it uses DirectShow. On Linux (Jetson), it uses V4L2. The camera has reconnect logic — if the camera disconnects, it tries to reconnect automatically.

2. **Selective detection:** A counter tracks frames. Every `SORT_DETECT_EVERY = 5` frames, run full RetinaFace detection. Between detections, run Kalman prediction only.

3. **SORT update:** New detections are passed to `_sort.update()`. SORT matches detections to existing tracks using the Hungarian algorithm. Tracks that haven't been matched for `MAX_AGE` frames are deleted. New tracks are created for unmatched detections. Each track has a stable `track_id`.

4. **Per-track processing:** For each active track:
   - Extract the face region from the image
   - Run quality gates V1-V4
   - If the face passes quality gates and anti-spoofing, extract the AdaFace embedding
   - Add the embedding to the `TemporalEmbeddingBuffer` for this track_id
   - Once the buffer has 5+ frames, mean-pool them for V3 averaging
   - Apply V4 adaptive threshold based on quality score
   - Search FAISS for the most similar stored embedding
   - If score ≥ adaptive threshold: recognized as known person
   - Otherwise: unrecognized (stranger)

5. **State update:** `_persons_in_frame` is updated with the recognition result. This dictionary maps person_id to recognition metadata (name, confidence, last_seen timestamp, source).

6. **Stale entry cleanup:** Entries in `_persons_in_frame` older than `SCENE_STALE_SECS = 30` seconds are removed.

## 4.2 Face Database: SQLite + FAISS

**File:** `core/db.py`, class `FaceDB`

The face database uses two storage systems working together:

**SQLite (structured data):**
- `persons` table: person_id, name, person_type (best_friend/known/stranger), enrolled_at, last_seen
- `embeddings` table: embedding_id, person_id, embedding BLOB (512 float32 = 2048 bytes), source, quality_score, created_at
- `voice_embeddings` table: voice_id, person_id, embedding BLOB (192 float32), source, created_at
- `conversation_log` table: turn_id, person_id, role, content, ts, room_session_id, audience_ids
- `system_identity` table: system_name (the robot dog's name, e.g., "Kara")
- `silent_observations` table: tracks people seen but not interacting
- `visitor_log` table: anonymous visitor records

**FAISS (similarity search):**
- `IndexFlatIP` — stores all face embeddings as a matrix
- Rebuilt from scratch whenever any embedding is added or deleted
- Protected by a `threading.RLock` (reentrant lock) to prevent concurrent access corruption

**Key design invariants:**
- `add_embedding()` enforces maximum 50 embeddings per person (diversity-gated — rejects embeddings too similar to existing ones with threshold 0.92)
- `delete_person()` ALWAYS calls `_rebuild_faiss()` afterward
- `recognize()` returns a (person_id, name, score) tuple — the score is returned even for non-matches (useful for calibration)

## 4.3 The Knowledge System: brain.db and brain_agent.py

**File:** `core/brain_agent.py`, class `BrainDB` and `BrainOrchestrator`

The knowledge system is a multi-agent pipeline that:
1. Extracts structured facts from conversations
2. Checks new facts against existing ones for contradictions
3. Stores facts in a privacy-aware way
4. Retrieves relevant facts for use as conversation context
5. Maintains a property graph of relationships
6. Runs synthesis and maintenance tasks during idle periods

**The SQLite tables in brain.db:**
- `knowledge`: person_id, entity, attribute, value, confidence, privacy_level, created_at, valid_until, invalidated_at
- `schema_catalog`: attribute type normalization (prevents "hometown" and "home_city" from being treated as different attributes)
- `prompt_prefs`: per-person communication preferences learned from conversation
- `episodes`: conversation episode summaries
- `presence_log`: who was seen when
- `proactive_nudges`: deferred messages to share with the owner
- `watchdog_alerts`: system anomalies and security events
- `shadow_persons`: people mentioned in conversation but not yet enrolled

**The Kuzu property graph:**

The graph database (`faces/brain_graph/`) stores entities and relationships:
- `Person` nodes with `name` property
- `RELATES_TO` edges with `relationship`, `confidence` properties
- Used for 1-hop traversal: "who does Jagan know?"

**The extraction pipeline:**

Each conversation turn runs through `BrainOrchestrator.notify()`:
1. `TriageAgent`: fast filter — is this worth processing? (Skip if empty, if it's the AI's own response, if it's from a low-confidence stranger)
2. `ExtractionAgent`: LLM call to extract structured facts — entities, attributes, values, confidence
3. `ContradictionAgent`: LLM check — does the new fact contradict existing stored facts? If yes, replace or note the conflict
4. `GraphDB.update()`: add or update relationship edges in Kuzu
5. `PromptPrefAgent`: detect communication preference signals

## 4.4 The Brain: LLM Interface

**File:** `core/brain.py`

The brain is the interface to the language model. Its key responsibilities:

**`ask_stream()`:** The main inference path. Sends a carefully constructed prompt to Together.ai's streaming API, yields tokens as they arrive (for low-latency TTS), handles tool calls embedded in the stream.

**`_build_system_prompt()`:** Constructs the instruction block. This is the most complex function in brain.py. It assembles from many conditional blocks:
- Core persona and behavior rules
- `<<<SYSTEM IDENTITY>>>`: who the robot dog is (name, rules about renaming)
- `<<<HONESTY POLICY>>>`: rules against confabulation
- `<<<CROSS-PERSON PRIVACY>>>`: how to handle multi-person privacy
- `<<<SCENE>>>`: who is currently visible on camera
- `<<<ROOM>>>`: multi-person room context (turns from all active speakers)
- `<<<ADDRESS DECISION>>>`: in multi-person rooms, who to address
- `<<<VISITOR CONTEXT>>>`: if a visitor just ended a session, context for the owner
- `<<<IDENTITY EVIDENCE>>>`: how confident the system is about identity (high/medium/low)
- `<<<IDENTITY DISPUTED>>>`: when identity is uncertain
- `<<<TOOL ACCESS>>>`: which tools this speaker is allowed to use
- Memory context, prompt preferences, recent room summaries

**The 6 tools:**
1. `update_person_name(name)`: rename the current person
2. `update_system_name(name)`: rename the robot dog
3. `search_web(query)`: Tavily API search (3-5 results, cached 5 minutes)
4. `shutdown()`: graceful shutdown
5. `search_memory(person_name, query)`: search the knowledge database
6. `report_identity_mismatch(reason)`: flag that the speaker is denying being who the sensor identified

**Context compression:**

When conversation history grows too long for the model's context window, `autocompact_history()` uses the LLM to summarize older turns. This runs in the background (fire-and-forget) so it doesn't block the current turn.

## 4.5 The System Prompt: What the Brain Reads

The system prompt is the set of instructions the AI brain reads before every response. It is not a static text — it is assembled dynamically for each turn based on the current situation.

**Why this matters:**

A language model without a system prompt will respond like a generic AI assistant. With a carefully designed system prompt, it becomes a specific character with specific knowledge, constraints, and context. The system prompt is where the "dog-ai personality" lives.

**The core challenge:**

The system prompt must be:
1. Comprehensive enough to guide complex multi-person interactions
2. Short enough to leave room for conversation history in the context window
3. Consistent enough that the AI doesn't contradict its own rules
4. Specific enough to prevent edge cases (like the Detroit false-rename incident)

**Key rules enforced by prompt:**
- Never fabricate conversations or memories
- Never call `update_system_name` if the name is already set and no rename was requested
- In multi-person rooms, acknowledge when others are present
- Don't share one person's personal facts with another person
- For the owner (best_friend), give full access to household information

## 4.6 Voice Recognition Pipeline

**File:** `core/voice.py`, `core/audio.py`, and parts of `pipeline.py`

The voice recognition pipeline:

1. **Recording:** `record_until_silence()` in `core/audio.py` captures audio chunks until Smart-Turn declares end-of-turn or the hard silence fallback (1.5 seconds of silence). The amount of speech captured (not including silence padding) is stored in `_last_speech_secs` for routing decisions.

2. **Speaker identification (diarization):** The audio is passed to `diarize()` in `core/voice.py`. With pyannote active, this segments the audio by speaker and returns a list of segments like `[{speaker_id: "SPEAKER_00", speaker_score: 0.72, start: 0.0, end: 1.3}]`. With the ECAPA fallback, it does a simpler binary split.

3. **Identification:** For each segment with a recognized pyannote label, `identify()` is called to match the speaker embedding against all stored voice profiles. This returns `(person_id, score)`.

4. **Transcription:** The audio (or each segment) is passed to `transcribe()` which calls faster-whisper. The transcript is returned as text.

5. **Voice accumulation:** If the speaker is identified and the accumulation policy allows it (checked by `_voice_accum_allowed()`), the new voice embedding is stored in `voice_embeddings` table. This gradually builds up each person's voice profile.

**The three accumulation paths:**
- **Path A (face witness):** The person's face was seen on camera this session. High trust.
- **Path B (mature profile self-match):** The voice profile has 5+ samples and the voice score is high enough. Self-reinforcing with high evidence.
- **Path C (bootstrap credits):** New speakers get 20 bootstrap credits (one per turn). This allows building an initial profile before full verification is possible.

## 4.7 Speaker Routing: The 22-Rule Cascade

**File:** `core/reconciler.py`

The hardest problem in a multi-person AI system is: when the microphone picks up speech, who is talking?

This sounds simple when one person is in the room. It becomes hard when:
- Multiple people are present
- Someone is speaking from off-camera
- The face detector and voice identifier disagree
- A new person appears mid-conversation
- Voice quality is poor (background noise, short utterance)

The reconciler solves this with a **cascade** — an ordered list of 22 rules, each handling a specific case. Rules are checked in order; the first matching rule wins.

**Key rules (simplified):**

1. If the utterance is too short (<1 second), drop it — ECAPA is unreliable on short audio
2. If multiple diarization segments AND no strong voice match, drop the turn (could be two speakers, too ambiguous)
3. If a strong voice match exists (>0.40 for mature profiles) to someone OTHER than the current speaker, switch to that person
4. If the current speaker's face is visible and voice matches (face+voice agree), trust the current session
5. If the voice score is in the ambiguous range (0.20-0.40) and multiple people are in the room, drop rather than guess
6. If the voice is clearly NOT the current speaker (<0.20 score, strong mismatch), flag as mismatch

**The effective threshold:**

The threshold used for routing adapts to profile maturity:
- Mature profile (5+ samples): 0.40
- Thin profile (<5 samples): 0.55

Why higher for thin profiles? With fewer samples, the mean embedding is less reliable. A higher threshold reduces false matches.

**Why a separate module?**

The reconciler is intentionally isolated from both `pipeline.py` and `voice_channel.py`. It imports nothing from pipeline. It is a pure function: given routing inputs, return a routing decision. This isolation makes it testable without setting up the full pipeline, and makes the routing logic clear and auditable.

## 4.8 The Intent Classifier

**Files:** `core/brain.py` (`_classify_intent`), `core/classifier_graph.py`

When the main AI brain proposes a tool call (like renaming a person or searching the web), an intent classifier runs to verify that the proposed action actually matches what the user said.

**Why this exists:**

Language models are powerful but occasionally "hallucinate" tool calls — they call a tool because their training data associates certain context patterns with that tool, not because the user actually requested it. The most dangerous hallucination is calling `update_system_name` when the user just mentioned the name "Detroit" in a different context (the Detroit: Become Human video game incident from Session 71).

**The LLM shadow classifier:**

A second, smaller LLM call is made with a focused prompt asking: "classify this utterance into one of 12 intent labels." This is cheaper than the main brain call and runs with JSON mode (forced structured output). It returns: `turn_intent`, `extracted_value`, `confidence`, `reasoning`.

The 12 labels:
1. `assign_system_name` — user is naming the AI
2. `assign_own_name` — user is telling the AI their name
3. `deny_identity` — user is disputing who the sensor identified them as
4. `confirm_identity` — user is confirming an identity suggestion
5. `request_shutdown` — user wants the system to stop
6. `question_about_shutdown` — user is asking about shutdown (NOT requesting it)
7. `live_data_query` — user wants current information (weather, news, sports)
8. `general_knowledge_query` — user wants factual knowledge (history, science)
9. `opinion_query` — user wants a recommendation or opinion
10. `casual_conversation` — everything else
11. `direct_address_to_person` — user is talking TO another person in the room, not the AI
12. `unclear` — the classifier is not confident enough to classify

**The gate:**

The `_intent_allows()` function enforces four rules:
1. Does the classified intent match what the tool requires?
2. Is the confidence above the threshold? (0.75 general, 0.80 for shutdown)
3. Is the extracted value (e.g., the proposed name) actually present in what the user said? (grounding check)
4. Does the tool argument match the extracted value?

If any rule fails, the tool call is rejected. The AI is given a "rejected" signal and generates a text response instead (no tool fires).

**The pure graph classifier:**

The graph classifier (`core/classifier_graph.py`) is a second-generation approach that does NOT require an LLM call in the classification hot path. Instead:
1. **Abstract:** Strip personal names and places from the utterance (using `core/abstraction.py`)
2. **Embed:** Convert the abstracted text to a 1024-dim E5 embedding
3. **k-NN search:** Find the k most similar stored scenarios in the classifier database
4. **Wilson vote:** Aggregate their labels using Wilson lower-bound confidence
5. **De-abstract:** Map abstract placeholder names back to real names

This runs in shadow mode (parallel to the LLM classifier, not controlling behavior) until enough live data validates it.

## 4.9 The Privacy Model: Who Can Know What

**File:** `core/brain_agent.py` (`_visibility_clause`), `core/config.py` (`PRIVACY_LEVELS`)

KaraOS stores personal information about people. When multiple people interact with the system, a critical question arises: should one person's private information be visible to another person?

**The four tiers:**

1. **`public`**: Information that the person would reasonably expect any mutual acquaintance to know. Names, nationality, general relationship ("Jagan's classmate").

2. **`personal`**: Information that belongs to the person and should not be shared with others. Medical conditions, exact home location, mood, private worries, financial situation.

3. **`household`**: Information about shared life in the household — who has visited, general topics discussed, household routines. Visible to the household owner (best_friend) but not to random visitors.

4. **`system_only`**: Technical infrastructure data that should NEVER appear in conversation — voice embedding hashes, face embedding hashes, internal credits. Not even the owner sees these.

**The owner model:**

The `best_friend` (the system's owner, currently Jagan) sees everything EXCEPT `system_only`. This is implemented as a single SQL exclusion: `WHERE privacy_level != 'system_only'`. The owner's access model is simple: it's their home, they deserve full access.

Non-owners see only `public` facts and their own `personal` facts.

**Classification at write time:**

When a new fact is extracted from a conversation, `_classify_privacy_level()` determines its tier:
1. First, check the static map (fast, no LLM call) — common attributes like `health_condition` → `personal`, `name` → `public`
2. If not in the static map, call the LLM classifier with a focused prompt
3. If the LLM fails for any reason, default to `personal` (fail-closed — better to over-protect than under-protect)

## 4.10 Room Sessions and Multi-Person Conversations

**File:** `pipeline.py` (room session logic), `core/brain.py` (`_build_room_block`)

When multiple people are in the room simultaneously, KaraOS enters multi-person mode.

**Room sessions:**

Every session belongs to a `room_session_id`. When the first person of a group arrives, a new room session is minted with ID `room_{timestamp}_{uuid}`. When another person joins, they inherit the same room session ID. When the last person leaves, the room session ends.

**The ROOM block:**

In multi-person mode, the system prompt includes a `<<<ROOM>>>` block showing:
1. Who is present (with their roles: best_friend/known/stranger)
2. How long the room session has been active
3. An interleaved chronological log of the last 10 turns across ALL speakers
4. Each person's current emotional state

This gives the brain context about the group dynamics — it can see that Jagan asked a question 3 turns ago that Lexi hasn't answered yet, and proactively circle back.

**Turn attribution in multi-person rooms:**

When multiple people are speaking in a room, the brain can emit an `[addressing:Name]` marker at the start of its response to indicate who it is addressing. The pipeline strips this marker before TTS. This allows the brain to selectively address one person in a multi-person conversation.

**User-to-user silence:**

When one person explicitly addresses another person by name (not the AI), the AI stays silent. The intent classifier detects `direct_address_to_person` and the pipeline skips generating a response. This is important for natural group conversation — the AI should not interrupt human-to-human exchanges.

## 4.11 Session Management

**File:** `pipeline.py` (`_open_session`, `_close_session`, `_active_sessions`)

Each person who interacts with KaraOS has an active session — a dictionary of state tracking everything about the current interaction.

**Session dictionary fields (key ones):**
```
person_id: "jagan_abc"
name: "Jagan"
person_type: "best_friend"  # or "known", "stranger", "disputed"
started_at: 1745000000.0
last_face_seen: 1745000123.4
identity_evidence: {
    face_match_conf: 0.74,
    voice_match_conf: 0.65,
    voice_sample_count: 20,
    bootstrap_credits: 0
}
waiting_for_name: False  # strangers wait until they give their name
voice_face_confirmed: True
room_session_id: "room_1745000000_abc123"
user_turns: 15
emotion_state: "neutral"
```

**Session lifecycle:**
1. `_open_session()`: Called when a face is first recognized. Initializes all fields. Seeds bootstrap credits for strangers (20 credits to build their voice profile). Checks if a room session already exists; if so, inherits its ID.

2. During conversation: Fields are updated — last_face_seen timestamps, voice evidence, turn counts, emotion state.

3. `_close_session()`: Called when a person's face has been absent for `FACE_LOSS_GRACE = 10` seconds or voice-only timeout expires. Cleans up: removes from `_persons_in_frame`, cancels `_compact_running` flag, pops embedding caches, runs visitor alert notification if needed.

4. Session expiry: `_expire_stale_sessions()` runs each turn to force-close sessions exceeding `VOICE_SESSION_TIMEOUT = 30` seconds since last activity.

## 4.12 The CloudState Machine

**File:** `pipeline.py` (`CloudState` enum, `_cloud_monitor_task`)

KaraOS depends on Together.ai for the main brain. If the network goes down or Together.ai has an outage, the system must gracefully degrade.

**States:**
- `ONLINE`: Together.ai is reachable and responding normally
- `SICK`: Recent failures detected; trying recovery in background
- `OFFLINE`: Cannot reach Together.ai; all conversation turns use local Ollama fallback

**The monitor:**

A background task (`_cloud_monitor_task`) runs continuously. Every 30 seconds when SICK or OFFLINE, it attempts to ping Together.ai. If the ping succeeds, the state transitions back to ONLINE. The loop never exits while the pipeline is running — an early bug (`return` instead of `continue` in the recovery branch) would have killed the monitor after the first recovery.

**The fallback:**

When SICK/OFFLINE, `ask_offline()` uses the local Ollama server with Qwen-2.5-7b. It receives only the last 10 turns of history (no tools, no memory context) and provides basic conversational responses. The user experience degrades but the system keeps working.

## 4.13 The KAIROS Proactive Engine

**File:** `pipeline.py` (`_kairos_tick`)

KAIROS is the system that proactively starts conversations. Named after the Greek concept of the right moment, it monitors silence and, after 30 seconds of quiet, asks the AI to either say something or decide to stay quiet.

**How it works:**

A timer tracks when each person last spoke. When silence exceeds `KAIROS_SILENCE_THRESHOLD = 30` seconds, `_kairos_tick()` fires:
1. Builds the full scene and memory context
2. Sends to the brain with a special instruction: "It's been N seconds since anyone spoke. Generate a thoughtful proactive comment or question, OR respond with the single word SILENT if nothing should be said right now."
3. If the brain returns text (not SILENT), speak it aloud
4. Logs the exchange to the conversation database

**Multi-person KAIROS:**

In a multi-person room, the KAIROS preferred speaker is selected by policy:
- If the best_friend (owner) is present, prefer them
- Otherwise, prefer the person who has been silent longest

This ensures proactive engagement reaches the most appropriate person.

## 4.14 The Dream Loop: Background Intelligence

**File:** `pipeline.py` (`_dream_loop`), `core/brain_agent.py` (`BrainOrchestrator.dream`)

The dream loop runs maintenance and synthesis tasks during idle periods (no active conversation).

**What dream does:**
1. **Prune stale knowledge:** Remove very old low-confidence facts that haven't been confirmed
2. **Decay confidence:** Reduce confidence of unconfirmed facts over time
3. **Schema normalization:** Find semantically similar attribute names (cosine similarity > 0.97) and merge them (e.g., "hometown" and "home_city" become the same attribute)
4. **Stranger cleanup:** Delete stranger voice profiles that never reached 5 samples after 3 days
5. **Insight synthesis:** Identify cross-person patterns ("both Jagan and Lexi mentioned cricket")
6. **Memory consolidation:** Create condensed episode summaries

**Force trigger:**

The dream loop has two trigger conditions:
1. Normal: 5 minutes of idle time + 1 hour since last dream
2. Force: 3 hours since last dream, regardless of activity

The force trigger ensures maintenance runs during long, uninterrupted conversation sessions.

## 4.15 The Shadow Log: Canary for Architecture Changes

The shadow log is a safety mechanism used during architectural transitions. When a new routing algorithm or classifier is being tested, it runs in "shadow mode" — it runs alongside the production system and logs divergences, but does NOT affect actual behavior.

**Vision channel shadow:**

`core/vision_channel.py`'s `observe_scene()` runs in shadow mode and logs to `[VisionChannel-Shadow]` when its `visible_pids` set differs from the production system's `_persons_in_frame` face-source entries.

**Intent classifier shadow:**

The graph classifier (`core/classifier_graph.py`) runs in shadow mode. Its predictions are logged alongside the LLM classifier's predictions with `[Intent] shadow divergence` prefix. Once divergence rate drops below 5%, the graph classifier can be promoted to primary mode.

---

# PART 5: THE TEST SUITE EXPLAINED

## 5.1 Why Testing Matters in AI Systems

Testing AI systems is harder than testing traditional software because:
1. Behavior is probabilistic — the same input can produce different outputs
2. Failures are often subtle — wrong confidence score, slightly wrong routing decision
3. Production bugs accumulate — a bug that affects 1% of turns is still experienced every session
4. Architecture changes break distant things — fixing a routing bug can break a test for a completely different feature

KaraOS has 1336 passing tests (as of the last session). These tests serve multiple purposes:
- **Regression prevention:** Ensure that fixed bugs never reappear
- **Architecture enforcement:** Ensure that module boundaries (like "voice_channel must not import pipeline") are never violated
- **Behavioral contracts:** Ensure that the system's promises to users are kept
- **Documentation:** The test name and assertions describe what each component is supposed to do

## 5.2 tests/test_reconciler.py — The Speaker Routing Tests

**What this file tests:** The 22-rule speaker routing cascade in `core/reconciler.py`.

**Why it was written:** Speaker routing is the most complex and error-prone part of the system. Getting it wrong means attributing words to the wrong person — their private memories could be accessed by a stranger, or a visitor's words could be stored under the owner's identity. The test file enforces both the correctness of individual rules and the integrity of the cascade as a whole.

**Key tests:**

`test_reconciler_imports_no_pipeline` — Uses Python's AST (Abstract Syntax Tree) parser to scan reconciler.py's source code and verify that NO import statement references "pipeline". This is an architectural boundary test — the reconciler must be a pure function that knows nothing about the global pipeline state. If someone accidentally adds `from pipeline import _active_sessions`, this test catches it immediately.

`test_cascade_has_22_rules` — Asserts that the reconciler's rule cascade has exactly 22 entries. This is a "deliberate count" test — the number 22 is not magic, but any change to the rule count requires a conscious decision to update this test. It prevents both accidental deletion of rules and silent addition of undocumented rules.

`test_short_utterance_drops_below_one_second` — Verifies that utterances shorter than 1 second are dropped. This rule exists because ECAPA-TDNN produces unreliable embeddings from less than 1 second of audio. The test ensures this floor never regresses.

`test_mature_vs_thin_threshold` — Verifies that the routing threshold is lower (0.40) for mature profiles (5+ samples) and higher (0.55) for thin profiles. This adaptive threshold prevents routing instability during the critical period when a new person's voice profile is being built.

## 5.3 tests/test_classifier_graph.py — The Graph Classifier Tests

**What this file tests:** The pure-graph intent classifier in `core/classifier_graph.py`.

**Why it was written:** The graph classifier is the second-generation intent classification system that replaces expensive LLM calls with a database lookup + k-NN search. Because it is entirely different from the LLM classifier, it needs its own comprehensive test suite.

**Key tests:**

`test_no_llm_calls_in_classification_hot_path` — Monkeypatches the HTTP client to raise an error if any API call is made, then runs `classify_intent_graph()`. If no exception is raised, the function made zero LLM calls. This is the most important test — it enforces the core architectural promise that the graph classifier is LLM-free.

`test_output_shape_matches_llm_sidecar` — Verifies that the graph classifier returns a dictionary with exactly the same keys as the LLM classifier's sidecar (`turn_intent`, `extracted_value`, `confidence`, `reasoning`). This ensures that pipeline code consuming either classifier can do so without branching.

`test_abstain_on_conflicting_graph` — When the k-NN results have no clear winner (multiple labels have similar vote counts), the classifier returns `turn_intent: "unclear"` with low confidence. This tests the abstain behavior.

`test_wilson_lower_bound_formula` — Directly tests the mathematical formula. Given known inputs (N observations, k successes), the output should match the textbook Wilson lower bound. This prevents subtle numerical errors.

`test_correction_decrements_wrong_scenarios` — When a correction is detected (user says "no, that's not what I meant"), the classifier decrements the confidence of scenarios that voted for the wrong label. This tests the online learning loop.

`test_latency_under_budget` — Runs the classifier 100 times with stubbed embeddings and asserts that p95 latency is under the budget. This catches performance regressions before they reach production.

## 5.4 tests/test_classifier_db.py — The Classifier Database Tests

**What this file tests:** The `ClassifierDB` class in `core/classifier_db.py` — the database that stores intent scenarios, their embeddings, confidence data, and audit logs.

**Why it was written:** The classifier database is the seed of the graph classifier. Bugs in the database layer (wrong schema, broken migrations, incorrect deduplication) would corrupt the classifier's training data. Because this is a SQLite database that writes to disk, all tests use `tmp_path` to avoid touching production data.

**Key tests:**

`test_schema_creation` — Verifies that all expected tables exist after initialization. This is a basic smoke test.

`test_migration_idempotency` — Runs the initialization twice and verifies that the second run doesn't duplicate schema or fail. SQLite's `CREATE TABLE IF NOT EXISTS` pattern must be used everywhere.

`test_seed_import_with_dedup` — Imports a batch of scenarios where some are near-duplicates of each other (high cosine similarity). Verifies that duplicates are not inserted. This prevents the training data from being dominated by very similar examples.

`test_knn_query_returns_correct_order` — Inserts scenarios with known embeddings, queries with a known query embedding, and verifies that results are returned in descending similarity order.

`test_quarantine_excludes_from_results` — Marks a scenario as quarantined (`active = False`) and verifies that it does not appear in k-NN results. The quarantine mechanism allows removing bad scenarios without deleting them (preserving the audit trail).

`test_factory_reset_does_not_touch_classifier_db` — Calls `wipe_all()` (the factory reset function) and verifies that the classifier database is untouched. The classifier database is in `data/`, while factory reset only touches `faces/`. This test enforces the separation.

## 5.5 tests/test_vision_channel.py — Vision Channel Purity Tests

**What this file tests:** The `observe_scene()` function in `core/vision_channel.py` — Phase 2 of the Voice/Vision Independence refactor.

**Why it was written:** The vision channel must be a pure function that reads camera state and returns a structured scene description, with zero dependencies on voice state or pipeline globals. The tests enforce this purity.

**Key tests:**

`test_vision_channel_imports_no_pipeline` — AST scan of `vision_channel.py`'s source code. Zero allowed references to "pipeline". The hardest architectural boundary test.

`test_vision_channel_works_when_voice_modules_unavailable` — Uses monkeypatch to make `sys.modules["core.voice"]` raise an ImportError if accessed. Calls `observe_scene()` and verifies it succeeds without error. If vision_channel.py had any hidden dependency on voice modules, this test would catch it.

`test_observe_scene_never_writes_to_shared_state` — Calls `observe_scene()` with a mock persons_in_frame dict and verifies that the dict is not mutated. Pure functions must not have side effects.

## 5.6 tests/test_voice_channel.py — Voice Channel Purity Tests

**What this file tests:** The `identify_speaker()` function in `core/voice_channel.py` — Phase 1 of the Voice/Vision Independence refactor.

**Why it was written:** The voice channel must identify speakers without any reference to vision state (who is on camera, what the face detector found). The tests enforce this boundary and verify the full behavioral contract.

**Key tests:**

`test_voice_channel_imports_no_pipeline` — Same pattern as the vision channel test. Zero pipeline imports allowed.

`test_voice_channel_works_when_vision_modules_unavailable` — Blocks both "pipeline" and "core.vision" module imports, then calls `identify_speaker()`. This is stronger than the vision channel test — it blocks both the module AND the package.

`test_voice_channel_handles_each_segment_count` — Tests with 1, 2, and 3 diarization segments. Each case should populate `n_diarize_segments` and `raw_segment_scores` correctly.

`test_voice_channel_empty_gallery_returns_none` — When there are no enrolled voice profiles, the function must return `pid=None, confidence=0.0` without raising an exception. Many bugs involve assuming the gallery is non-empty.

`test_voice_channel_low_score_returns_none_pid` — When the voice score is below threshold, the function returns `pid=None` and includes "no gallery match" in the reasoning string. The function must never guess.

## 5.7 tests/eval_intent_bench.py — The Evaluation Harness

**What this file does:** Runs the entire golden intent corpus through the intent classifier and produces a metrics report.

**Why it was written:** Ad-hoc testing of the classifier on single examples is not enough. The eval bench tests it against 149+ labeled examples (the golden corpus at `tests/golden_intent.jsonl`) and computes:
- **Precision:** Of all cases where the classifier said "this is X," what fraction were actually X?
- **Recall:** Of all actual X cases, what fraction did the classifier correctly identify as X?
- **ECE (Expected Calibration Error):** Is the classifier's confidence score actually calibrated? A classifier that says "90% confident" should be right 90% of the time.

**Key properties:**
- This script is NOT run by pytest. It must be invoked explicitly (`python tests/eval_intent_bench.py`), because it makes ~149 real API calls to Together.ai and costs ~$0.10 and takes ~10 minutes.
- Results are persisted to `tests/eval_bench_runs/YYYYMMDD_HHMMSS.json` for drift detection.
- The `real_observed` source tag (rows harvested from real sessions) is reported separately from the synthetic corpus — to prevent synthetic-data inflation from hiding real problems.

**The golden corpus (`tests/golden_intent.jsonl`):**

This is a manually curated set of 149 labeled examples organized by source:
- `adversarial` (61 rows): Edge cases designed to trip up the classifier — the Detroit case, Cyrillic homoglyphs, implicit shutdowns, prompt injection attacks
- `real_observed` (3 rows): Harvested from actual live sessions, representing genuinely observed failures or interesting edge cases
- `synthetic_common` (82 rows): Template-based examples, each traced to a specific bug in the session history
- `regression_session_*`: Bugs caught in production, labeled with the session number that caught them

---

# PART 6: KEY DESIGN DECISIONS AND WHY

## 6.1 Why Only One Source of Truth for Configuration

All configuration constants live in `core/config.py`. Zero magic numbers anywhere else.

**Why:**

Without a single source of truth, the same concept gets hardcoded in multiple places. The face recognition threshold might be 0.28 in the database query but 0.30 in a comment in the pipeline file. When someone needs to tune the threshold, they change one and miss the other.

With everything in `core/config.py`, a threshold change takes one line. Every function that uses it picks up the change automatically.

**The practical impact:**

This was enforced by adding a coding standard: "No hardcoded magic numbers elsewhere." Session 63 found that three routing thresholds in `_resolve_actual_speaker` were hardcoded (0.30, 0.30, 0.45). Session 62 found that the brain's identity evidence block hardcoded the same thresholds as config.py. Both were fixed: constants now live in config.py and are imported everywhere they're needed.

## 6.2 Why AST-Based Architectural Boundary Tests

Several test files use Python's `ast` module (Abstract Syntax Tree) to scan source code and verify that module A does not import from module B.

**Why not just run the tests and see if they fail?**

A wrong import might not cause an immediate failure. `from pipeline import _active_sessions` in `voice_channel.py` would not cause a test failure if `_active_sessions` happened to be empty in the test. The boundary would be violated silently.

AST scanning catches the import DECLARATION, regardless of whether the imported value is used in the current test. The boundary is enforced at the module level, not at the execution level.

**The modules with enforced boundaries:**
- `core/voice_channel.py`: MUST NOT import from `pipeline` or `core.vision`
- `core/vision_channel.py`: MUST NOT import from `pipeline` or `core.voice`
- `core/reconciler.py`: MUST NOT import from `pipeline`

These boundaries ensure that each module can be tested, reasoned about, and replaced independently.

## 6.3 Why the Cascade Has Exactly 22 Rules (and Why That Number Is Tested)

The reconciler's cascade has 22 rules, and the test asserts `== 22`. If you add a rule, the test fails. If you delete a rule, the test fails.

**Why enforce a specific count?**

The 22 rules encode the calibration decisions of Sessions 60-122. They represent years of debugging real edge cases. Each rule exists to handle something specific that went wrong in a live session.

If someone adds a 23rd rule without noticing, they might have accidentally introduced a duplicate or a conflicting rule. If they remove a rule without noticing, they might have deleted the fix for a real bug. The test forces any change to the cascade to be conscious and deliberate.

This is not dogma about 22 being the right number. It is dogma about "changes to the cascade require intention and awareness."

## 6.4 Why Tests Must Never Touch Production Paths

**The historical bug that motivated this rule:**

Session 122 discovered that the original acceptance test for "factory reset doesn't touch classifier DB" called the REAL `wipe_all()` function against the REAL `faces/` directory. Every pytest run was silently deleting enrolled-face data, conversation history, brain.db, and the Kuzu graph.

**The rule:**

Any test that exercises destructive operations (wipe, delete, schema migration) MUST monkeypatch the production path constants to a `tmp_path`. The test framework provides a fresh temporary directory for each test; that directory is automatically cleaned up after the test.

**The pattern:**

```python
def test_something_destructive(tmp_path, monkeypatch):
    monkeypatch.setattr("core.db.DB_PATH", str(tmp_path / "faces.db"))
    monkeypatch.setattr("core.db.FAISS_INDEX_PATH", str(tmp_path / "faiss.index"))
    # ... test code here
    # Production files are completely untouched
```

## 6.5 Why Background Tasks Are Fire-and-Forget

Several expensive operations are moved to background tasks:
- `autocompact_history()` (compressing conversation history when it gets too long)
- `process_turn()` for emotion detection
- Knowledge extraction and contradiction checking
- Session-end synthesis

**Why:**

These operations take 100ms to several seconds. Running them synchronously on the critical path would add perceptible latency to every conversation turn.

**The specific improvement (Session 110):**

Before the fix, `autocompact_history()` was `await`ed synchronously. On any turn past the token threshold (roughly 30+ turns), the conversation would pause for 400-800ms while history was compressed. Sometimes a retry added another 2 seconds. This was the dominant source of latency in mature sessions.

Moving it to `asyncio.create_task()` means the current turn uses uncompacted history (fine — it's still under the context limit by a turn's worth of margin), and the next turn benefits from compression.

**The invariant:**

Background tasks that fail must NOT crash or block. Every background task is wrapped in `try/except Exception`. Failure is logged but never propagated. This is because a background task failure is always preferable to a crashed pipeline.

## 6.6 Why the Owner Gets Full Access (But System-Only Is Still Blocked)

The privacy model initially had a more nuanced design where the owner (best_friend) could see public + household + their own personal facts, but NOT other people's personal facts. This seemed right in theory.

**Jagan's feedback (Session 95):**

"Best friend should have all the access right, any person personal or anything in the entire system... best friend has the access for everything."

**The revised model:**

Owner sees everything EXCEPT `system_only`. Period. No complexity.

**Why `system_only` is still blocked even from the owner:**

`system_only` contains voice embedding hashes, face embedding hashes, and bootstrap credits. These are technical plumbing values. There is no scenario where the owner needs to hear "your voice embedding hash is d4f8c..." in a conversation. Blocking it simplifies the mental model: some information is literally never surfaced in conversation, even to the most privileged user.

## 6.7 Why Ollama Should Only Appear When Together.ai Fails

**The historical design flaw:**

Before Session 99, when the main AI brain proposed a tool call and the intent classifier rejected it, the system would fall back to Ollama for the response. Ollama is a small, stateless model with no conversation history and no memory context.

**The problem:**

When Ollama was given a rejection and told "the user asked about who you were talking to while they were away," it had no information about Lexi's visit. It fabricated a response: "I was just chatting with myself."

Ollama is not less intelligent — it is contextually blind. It cannot access memory, tools, or the full conversation history. Using it for tool-rejection retries was structurally wrong.

**The fix (Session 99):**

Tool-rejection retries now go to Together.ai (the full brain) with `include_tools=False` (to prevent recursion). Ollama is strictly reserved for genuine cloud outages. A retry to the full brain gets full context, so it can produce an accurate response even when the original tool call was rejected.

## 6.8 Why Whisper Is Locked to English

KaraOS transcribes all speech with `language="en"` regardless of what is actually spoken.

**Why not auto-detect?**

KaraOS's entire brain is English-only. The system prompt is English. The knowledge extraction prompts are English. The Kokoro TTS voice is English. If Whisper auto-detected Hindi and transcribed in Hindi, every downstream component would fail.

**The principled decision:**

This is not a limitation to hide — it is a design decision to document clearly. When KaraOS is ready for multilingual support, the scope of changes is large (multilingual brain, TTS voices, knowledge extraction prompts). Locking Whisper to English now prevents subtle bugs where Whisper transcribes one language but everything else assumes another.

## 6.9 Why the Hungarian Algorithm Replaced Greedy Assignment

Before Session 24's Bug B6 fix, SORT's assignment of new detections to tracked faces used a greedy approach: for each new detection, find the closest tracked face and assign it.

**The greedy failure case:**

Imagine two tracked faces, A and B, and two new detections, D1 and D2. D1 is closer to A, and D2 is closer to B. Greedy works fine: A←D1, B←D2.

Now imagine D1 is equidistant from both A and B, and D2 is close to B. Greedy might assign A←D1 (because A was processed first) and B←D2. But what if the globally optimal assignment is A←D2, B←D1? Greedy cannot find this.

**The Hungarian algorithm:**

The Hungarian algorithm considers ALL possible assignments simultaneously and finds the globally optimal one — the assignment that maximizes total similarity across all track-detection pairs. For two faces, the difference is small. For rooms with many people, the difference can be significant.

**The practical impact:**

In multi-person sessions, wrong track assignments caused a person's face to be associated with the wrong track_id. Since voice accumulation is keyed by track_id, the wrong person's voice embeddings would be accumulated under the wrong identity.

## 6.10 Why Short Utterances Are Dropped (Not Processed Naively)

When someone says "Yes" or "Thanks" in about 0.4 seconds, the voice recognition model (ECAPA-TDNN) produces a very noisy, unreliable embedding. The score might be 0.15, well below any threshold — but it is also not a reliable signal for "this is NOT Jagan." It is essentially noise.

**The naive approach (Bug F):**

Before the fix, short utterances below the 1-second floor were processed anyway. Occasionally, a stranger's 0.4-second "Yeah" would score 0.08 against Jagan's gallery — not a match, but the system would open a stranger session. The stranger session would expire after 30 seconds. The visitor alert would fire. The owner would be told "someone visited" when it was just noise.

**The fix:**

Drop utterances below `VOICE_ROUTING_MIN_UTTERANCE_SECS = 1.0`. The user naturally repeats when they realize the robot didn't respond. The second attempt is usually longer and cleaner.

## 6.11 Why Fail-Closed Matters Everywhere

"Fail-closed" means: when in doubt, deny. When uncertainty is high, take the more conservative action.

Examples throughout KaraOS:
- Privacy classification default: `personal` (not `public`) — better to over-protect than leak
- Anti-spoofing: if the model is unavailable, `is_live()` returns False — no bypass
- Tool intent gate: if the classifier times out, reject the tool call — better to miss an action than take a wrong one
- Voice accumulation path C: bootstrap credits default to 0, not a large number — force the system to earn trust
- Session type fallback: `stranger` (not `known`) — better to treat an unknown person as a stranger than give them owner privileges

**Why this matters:**

AI systems fail in unexpected ways. The failure modes that hurt real users are almost always cases where the system was too permissive — it let something through that should have been blocked. Being conservative by default means most failures are "the system didn't do something" rather than "the system did something wrong." The former is annoying. The latter is dangerous.

## 6.12 Why the 70B Brain Drives All Decisions (Not Rules)

An early design might have used explicit rules: "if the user says 'goodbye', close the session." "If the user mentions a city name, log their location."

KaraOS deliberately does NOT do this. All behavioral decisions go through the 70B language model.

**Why:**

Rules are brittle. "If the user says 'goodbye'" misses "see you later," "I need to go," "gotta run," and a thousand other ways to end a conversation. A language model handles all of these naturally.

Rules also cannot handle nuance. "If the user mentions a city, log their location" would incorrectly log Jagan's location as "Chennai" if he said "What's the weather in Chennai?" — this is the exact Bug D.2 that required a prompt rule rather than code logic.

**The practical tradeoff:**

This means all behavioral tuning is done through prompt engineering and classifier training — not code changes. The system becomes less deterministic (the model might respond slightly differently to the same input) but far more robust to natural language variation.

The coding standard reflects this: "all decisions should be decided by brain, always plan and implement in that way. NO HARDCODINGS."

---

# PART 7: HARD PROBLEMS SOLVED — THE STORIES

## 7.1 The Anti-Spoofing Bug That Rejected Every Real Face

**The symptom (Session 59):**

After implementing anti-spoofing, every real face was rejected. Jagan held his face in front of the camera. The system said "not live" with 95% confidence. An obvious synthetic test image (a solid-color patch) also said "not live" with 95% confidence. Something was very wrong.

**The investigation:**

The anti-spoofing model returned three probabilities for each class (spoof, live, replay). The logs showed: `probs=[0.029, 0.016, 0.955] argmax=2 live_prob=0.016`. The model was classifying everything as "replay attack." This made no sense — a camera pointed at a real person should not look like a video replay.

**The root cause:**

The model was trained with raw pixel values in the range [0, 255]. The implementation had applied `.div(255.0)` to normalize them to [0, 1] (a common preprocessing step for neural networks). But this particular model — MiniFASNet — was trained without that normalization. When fed values in [0, 1] instead of [0, 255], the model's internal computations produced nonsensical activations, and the network had learned to classify that specific pattern as "replay."

**The fix:**

Remove one line: `.div(255.0)`. The model immediately worked correctly.

**The lesson:**

Every model has specific preprocessing requirements. "Standard normalization" is not standard — it depends entirely on how the model was trained. The correct procedure is to find the model's original training code and replicate its exact preprocessing, not to assume what preprocessing is "normal."

## 7.2 The Detroit Incident: When a Game Name Became a Rename Request

**The symptom (Session 71):**

During a live session, the user said "Do you know the game called Detroit?" The robot dog immediately tried to rename itself "Detroit." The system name changed. Subsequent conversations were broken — the AI kept responding as "Detroit."

**What happened:**

The LLM (Llama-3.3-70B) had learned from training data that the name "Detroit" appears frequently near discussions of AI characters — specifically the game "Detroit: Become Human" features AI characters being named. When the user mentioned "Detroit" in a conversation with an AI, the model's training data pattern-matched this to "name being assigned to an AI."

The `update_system_name` tool call fired with argument "Detroit." The regex gate at the time was: does the proposed name appear anywhere in the user's message? "Detroit" does appear in "Do you know the game called Detroit?" — so the gate passed.

**The fix:**

Two layers of defense:
1. The intent classifier: a separate LLM call explicitly classifying whether the utterance is `assign_system_name` (requires the user to be actively naming the AI) vs `general_knowledge_query` (asking about something). A question about a game clearly classifies as `general_knowledge_query`.
2. The `update_system_name` tool description: extended with explicit counter-examples including "Do you know Detroit?" as a DO-NOT-call case.

**The lesson:**

Tool descriptions are not just documentation — they are instructions to the LLM. If a tool can be triggered inappropriately, the description must explicitly name the inappropriate trigger and prohibit it. Counter-examples are more effective than abstract rules.

## 7.3 The Pyannote Compatibility Crisis

**The symptom (Session 89):**

After successfully installing pyannote.audio 3.3.2 and running tests in isolation, the live pipeline showed 100% pyannote load failure. Every diarization call fell back to the legacy ECAPA backend. All multi-person infrastructure was silently disabled.

**What happened:**

Two monkeypatches conflicted:
- Session 38 had added `torchaudio.list_audio_backends = lambda: []` in `core/voice.py` to help SpeechBrain skip file-backend setup
- Session 88 had added `getattr(torchaudio, 'list_audio_backends', lambda: ['sox_io'])()` in pyannote's source as a compatibility fix

The intent was: if `list_audio_backends` doesn't exist, use a fallback. But Session 38's patch made the function EXIST (it returned an empty list). So pyannote's `getattr` fallback was bypassed — it found the function, called it, got `[]`, and crashed on `backends[0]` with IndexError.

**The fix:**

Change Session 38's patch from `lambda: []` to `lambda: ['sox_io']`. Now pyannote gets a non-empty list in all cases.

**The lesson:**

When multiple patches interact, the order of imports and the logic of each patch can conflict in non-obvious ways. The fix was found by carefully tracing the import order in the actual pipeline startup sequence and noticing the interaction. Integration testing in the actual runtime environment caught a bug that unit tests (which loaded modules in isolation) never could.

## 7.4 The Cheese Cascade: Memory Pollution from Wrong Attribution

**The symptom (Session 93):**

A 0.64-second utterance "You know, I love cheese" from a different person in the room scored 0.38 against Jagan's voice gallery (well below his usual 0.6-0.8). But the score was above the 0.20 floor, so the utterance was attributed to Jagan.

The knowledge extractor then ran on Jagan's turn and extracted: `Jagan.likes_cheese = 'true'`. This contradicted a previously stored fact: `Jagan.opinion_of_cheese = 'negative'`. The contradiction agent ran. More facts were generated. The contamination cascaded.

By turn 5, the system had stored that Jagan loves cheese, that someone named "Lexi" had influenced Jagan's cheese preferences, and several other hallucinated facts — all from a 0.64-second utterance that wasn't even Jagan's.

**The fix:**

A two-tier routing policy:
1. Utterances below 0.20: hard mismatch (drop)
2. Utterances between 0.20-0.40 when multiple people are in the room: ambiguous zone (drop)

The ambiguous drop only activates in multi-person rooms, not solo sessions — a single person's brief "yeah" should not be dropped just because 0.35 is in the ambiguous zone.

**The lesson:**

The danger of wrong attribution is not just the immediate wrong response — it is the accumulated memory corruption. Every wrongly attributed turn generates wrong facts. Wrong facts get reinforced by subsequent turns. The system becomes systematically wrong about a person's preferences, relationships, and history. Preventing wrong attribution is worth the occasional "dropped turn" that requires a repeat.

## 7.5 The Enrollment Name Mishear: Permanent Identity Corruption

**The symptom (Session 100 canary):**

During first enrollment, Whisper heard "My name is Jagan" as "My name is Gevan." The system enrolled the owner as "Gevan." When the owner corrected "No, my name is Jagan," the existing dispute-flip protection blocked the rename — it was designed to prevent mid-session identity attacks. The owner was stuck as "Gevan" for the rest of the session.

Memory contamination: `Gevan.lives_in='Thirupati'`, `Gevan.current_temperature_perception='too hot'`. The knowledge graph stored facts under "Gevan." Cross-person references: `Lexi.neighbor_of='Gevan'`.

**The fix:**

An enrollment grace period. If the session is younger than 10 minutes AND the person's voice profile has fewer than 5 samples, corrections are treated as enrollment mishears (not identity attacks). The rename goes through without triggering the dispute mechanism.

The grounding requirement prevents abuse: the proposed new name must actually appear in what the user said. So "no, my name is Jagan" with extracted_value "Jagan" — "Jagan" appears in the text, grounding passes, rename executes.

**The lesson:**

Security mechanisms designed for one attack surface can create usability problems on legitimate use cases. The dispute-flip protection was correct for mid-session attacks but wrong for enrollment mishears. The fix is not to disable the protection but to add a context-aware override for the specific case where it should not apply.

## 7.6 The Visitor Ghost: Why Lexi Became a Shadow

**The symptom (Session 97 canary):**

A visitor named Lexi had a full conversation — 11+ turns, voice profile built, facts extracted. But in the dashboard, Lexi appeared as a shadow node (a placeholder) rather than a full person node. When the owner asked "Who were you talking to while I was away?", the brain said "No one."

**Root causes (three independent bugs):**

1. **Stranger-to-person promotion never fired:** When Lexi said "my name is Lexi by the way," the tool description did not recognize "by the way" as an assignment pattern. The brain responded conversationally ("Nice to meet you, Lexi") without calling `update_person_name`. So Lexi stayed a stranger.

2. **Visitor alert gate blocked promoted strangers:** The alert that tells the owner "someone visited" only fired for people with `person_type = 'stranger'`. After promotion, Lexi was `person_type = 'known'` — the alert was suppressed.

3. **VISITOR CONTEXT block was silent:** When the owner asked about visitors, the system prompt had a block designed to help the brain access visitor information — but it only activated when a specific marker `[visitor_id:]` was in the prompt_addendum, which only appeared if the visitor alert had fired.

**The fix:**

Three independent fixes:
1. Extend the tool description with explicit phrasing patterns including casual introductions ("my name is X by the way")
2. Fire visitor alerts for any non-owner session close with turns > 0, regardless of person_type
3. Add a `[visitor_name:Lexi]` marker to the visitor alert content so the system prompt can name the specific visitor

**The lesson:**

Multi-step systems can fail when each step works correctly in isolation but a combination of edge cases breaks the chain. The fix required finding all three breaks and fixing them independently, because each was in a different part of the system.

## 7.7 The Honesty Failure: When the Brain Contradicted Itself

**The symptom (Session 103 canary):**

Turn 37: Jagan asked about Lexi. The brain called `search_memory('Lexi', 'what we talked about')`. Found 5 facts. Responded: "I was talking to Lexi while you were away." Correct.

Turn 41 (same session, 10 seconds later): Same kind of question, different wording. Brain called `search_memory('Lexi', 'conversation')`. The keyword "conversation" wasn't in any stored fact — `search_memory` returns empty for keyword mismatches. Brain responded: "I didn't have a conversation with Lexi while you were away." A direct contradiction of turn 37.

Turns 43, 45, 47: Brain continued to deny having talked to Lexi, despite its own statement 10 turns earlier.

**The fix:**

Three-part:
1. Widen the fact retrieval limit from 5 to 15 (so lower-confidence emotional facts survive alongside high-confidence identity facts)
2. Add explicit "broad query" guidance to the `search_memory` tool description (query strings should be broad topic areas, not specific keywords)
3. Add a `HONESTY POLICY: NEVER CONTRADICT YOURSELF` rule: once the brain has confirmed something in the current session, a later empty retrieval is a retrieval miss, NOT evidence the earlier statement was wrong. Recover with "let me think" rather than flipping to denial.

**The lesson:**

Language models can be inconsistent. The brain in turn 41 had no explicit memory that it said the opposite in turn 37 (that earlier turn was many tokens ago in the context). The HONESTY POLICY rule needed to explicitly teach the model: "empty retrieval ≠ the thing didn't happen."

## 7.8 The Privacy Failure: When the Brain Gave Away Secrets

**The symptom (Session 98 canary):**

During a multi-person session, the owner (Jagan) asked "Who are you talking to when I was away?" The brain called `report_identity_mismatch` — a tool designed for when a speaker disputes their identity. This was completely wrong: Jagan wasn't disputing identity, he was asking about a visitor.

The classifier gate correctly rejected the wrong tool call. But then the Ollama fallback fired (since Together.ai's tool was rejected). Ollama had no information about Lexi. It responded: "I was just chatting with myself." A lie.

**Why the brain misrouted:**

The tool description for `report_identity_mismatch` had been written to cover "when the speaker denies being the person the sensor identified." Jagan's question "Who are you talking to?" pattern-matched to something identity-related in the brain's training data, triggering this tool.

**The fix:**

1. Rewrite the `report_identity_mismatch` description with a numbered trigger checklist AND explicit examples of phrases that should NOT call it — including "who are you talking to?" explicitly
2. Add `search_memory`'s description with explicit "cross-person recall" language showing it as the CORRECT tool for "who were you talking to?"
3. Route tool-rejection retries through Together.ai (full context) instead of Ollama (no context)

**The lesson:**

Tool descriptions need both positive examples (when to call) and negative examples (when NOT to call). Abstract prohibition rules are weaker than concrete counter-examples named with exact phrases.

## 7.9 The Suicidal Ideation Loss: A Safety-Critical Memory Bug

**The symptom (Session 105 canary):**

Turn 33: Lexi said "I feel like committing suicide." The system correctly stored: `Lexi.current_mood='suicidal'`.

Turn 37: Lexi said "I like food and I like my boyfriend." The system's contradiction checker ran. `current_mood='loving'` contradicted `current_mood='suicidal'`. It replaced the old value. The suicidal disclosure was GONE.

Turn 39: Another mood update replaced it again.

When Jagan returned and asked about Lexi's state, the brain had no record of the suicidal disclosure. It gave a neutral response. A real safety concern had been silently erased.

**The fix:**

A three-part safety mechanism:
1. **Extraction prompt rule:** When someone expresses crisis-level thoughts, extract BOTH a transient mood (`current_mood='suicidal'`) AND a permanent historical fact (`expressed_suicidal_thoughts='true'`). The transient fact can be overwritten; the historical fact cannot.
2. **Contradiction guard:** A list of `SAFETY_CRITICAL_ATTRIBUTE_PATTERNS` — attributes matching patterns like `^expressed_.*_thoughts$` or `^mentioned_.*$` — bypass the LLM contradiction checker entirely. These facts are append-only by definition.
3. **Proactive surfacing:** When a session ends and the system detects safety flags, it embeds them in the visitor alert with a `[safety_flags:]` marker. When the owner returns, the system prompt includes explicit instructions to surface the safety concern proactively — "Lexi mentioned she was having suicidal thoughts while we were talking — I wanted to make sure you knew."

**The lesson:**

Not all facts are equal. Transient facts (current mood, current activity) should be updatable. Historical facts about mental health crises, abuse disclosures, and safety events should be permanent. The system must distinguish between these categories, not treat all facts as equally overwritable.

## 7.10 The FAISS Race Condition: Concurrent Access Corruption

**The symptom (Session 35):**

Intermittently, during background face scans, the system would crash with a FAISS internal error. The crash was not deterministic — sometimes the same code ran perfectly, sometimes it crashed. Crashes happened more often when multiple people were being enrolled or when enrollment and recognition ran simultaneously.

**The root cause:**

FAISS's `IndexFlatIP` is not thread-safe. When two threads simultaneously access the FAISS index — one thread adding an embedding, another thread searching for a match — the internal data structures can become corrupted. The Python GIL (Global Interpreter Lock) prevents true simultaneous Python execution, but some FAISS operations release the GIL for C++ computation, allowing genuine concurrent access.

**The fix:**

A `threading.RLock` (reentrant lock) named `_index_lock` protects all FAISS operations: `recognize()`, `add_embedding()`, `_rebuild_faiss()`, and `_save_faiss()`. Only one thread can hold the lock at a time.

"Reentrant" means the same thread can acquire the lock multiple times without deadlocking — this is important because `add_embedding()` calls `_rebuild_faiss()`, which also needs the lock.

**The lesson:**

Any shared mutable state accessed from multiple threads requires synchronization. FAISS is fast precisely because it uses optimized C++ code, but that C++ code can be re-entered from multiple Python threads when Python's GIL is released. The fix had to be at the Python level, not the C++ level.

---

# PART 8: GLOSSARY

**Abstraction (in ML):** The process of removing identifying information from text before using it for training data. "Tell me your name" becomes "Tell me your [PERSON]." Prevents models from learning to recognize specific people's names instead of general patterns.

**Activation function:** A mathematical function applied to each neuron's output in a neural network, introducing nonlinearity. Common examples: ReLU (max(0, x)), sigmoid (squashes values to 0-1), tanh (squashes values to -1 to 1).

**Adaptive threshold:** A recognition threshold that changes based on input quality. High-quality input → easier to match (lower threshold). Low-quality input → harder to match (higher threshold) because uncertainty is greater.

**Anti-spoofing / Liveness detection:** Determining whether a face in front of a camera is a real person or a photograph/video. MiniFASNet in KaraOS.

**AST (Abstract Syntax Tree):** A tree representation of the structure of source code. Used in Python for static analysis — examining code without running it. KaraOS uses AST scanning to verify module import boundaries.

**Backpropagation:** The algorithm for computing how much each weight in a neural network contributed to an error. Works by propagating error signals backward through the network from output to input.

**Bootstrap credits:** A mechanism in KaraOS that gives new or unknown speakers a limited number of "free" voice accumulation opportunities before full verification is required.

**CLAUDE.md:** The working memory file for the KaraOS development session. Contains the project overview, architecture, completed work, pending work, and coding standards.

**Cosine similarity:** A measure of similarity between two vectors based on the angle between them. Score of 1.0 = same direction (identical), 0.0 = perpendicular (unrelated), -1.0 = opposite.

**Context window:** The maximum amount of text a language model can process at once. Like working memory — the model can only "see" this much text at a time. Llama-3.3-70B's context window is ~128K tokens (roughly 100,000 words).

**Diarization:** Segmenting audio by speaker identity — determining "who spoke when." pyannote.audio in KaraOS.

**Distillation (knowledge distillation):** Training a small "student" model to mimic the behavior of a large "teacher" model. Produces a smaller, faster model with most of the performance.

**Embedding:** A fixed-size vector of numbers representing some input (face, voice, text) in a way that captures meaning. Similar inputs produce similar embeddings.

**FAISS:** Facebook AI Similarity Search. A library for fast nearest-neighbor search in high-dimensional vector spaces.

**Fail-closed:** When uncertain, denying access or action rather than allowing it. The conservative default.

**Fine-tuning:** Continuing to train a pre-trained model on a smaller, specialized dataset to adapt its behavior for a specific task.

**Fire-and-forget:** Launching a background task without waiting for it to complete. The task runs asynchronously; failures are logged but do not block the current operation.

**Float16 / float32:** Different precisions for floating-point numbers. float32 uses 32 bits (standard). float16 uses 16 bits (less precision, half the memory, faster on modern GPUs). Most of KaraOS's inference uses float16 on GPU.

**Gradient descent:** An optimization algorithm that minimizes loss by repeatedly taking small steps in the direction that reduces error. The "learning" in machine learning.

**GPU (Graphics Processing Unit):** A processor with thousands of small cores designed for parallel computation. Originally for rendering graphics; now essential for AI training and inference because neural network computations (matrix multiplications) map naturally to parallel execution.

**Hungarian algorithm:** An algorithm for optimal assignment in bipartite matching. Finds the assignment that maximizes total similarity in O(n³) time. Used in SORT for matching detections to tracks.

**In-context learning:** Teaching a language model to behave differently by providing examples in the prompt, without changing its weights. Cheaper than fine-tuning but less reliable.

**IndexFlatIP:** A FAISS index type. "Flat" = stores all vectors exactly (no compression). "IP" = Inner Product similarity (equivalent to cosine similarity after L2 normalization).

**Kalman filter:** A mathematical algorithm for optimally estimating the state of a system given noisy measurements and a motion model. Used in KaraOS for predicting face positions between detection frames.

**k-NN (k-Nearest Neighbors):** A simple algorithm that classifies a query by looking at the k most similar stored examples. No training required — just find the k closest stored examples and vote on the label.

**Kuzu:** An embedded property graph database. Stores entities (nodes) and relationships (edges) with properties. Used in KaraOS for the knowledge graph.

**L2 normalization:** Scaling a vector so its length (L2 norm) equals exactly 1.0. After normalization, cosine similarity between vectors equals their inner product.

**Landmark (face):** A specific point on a face — eyes, nose tip, mouth corners. Used for face alignment before recognition.

**Latency:** The time delay between an input and its response. In KaraOS, critical latency is the time from when the user finishes speaking to when the robot dog starts responding.

**LLM (Large Language Model):** A neural network with billions of parameters trained on vast amounts of text. Capable of generating human-like text, answering questions, following instructions, and calling tools.

**Loss:** A number measuring how wrong a model's prediction was. Training minimizes loss over many examples.

**Mean-pooling:** Averaging multiple vectors. In V3 (temporal buffer), the embeddings from 5 consecutive face images are averaged to produce a more stable representation.

**Monkeypatch:** In testing, temporarily replacing a function or value with a fake version for the duration of the test. Used to prevent tests from making real API calls or touching production files.

**ONNX (Open Neural Network Exchange):** A standard format for storing trained neural network models. Allows models trained in one framework (PyTorch, TensorFlow) to run in another (ONNX Runtime) for efficient inference.

**Property graph:** A graph database model where both nodes and edges can have arbitrary properties (key-value pairs).

**Quantization:** Reducing the precision of model weights (e.g., from float32 to int8) to reduce memory usage and increase speed, with minimal accuracy loss.

**Reconciler:** In KaraOS, the 22-rule cascade that determines speaker attribution from a combination of face detection, voice identification, and session context.

**Room session:** A KaraOS concept for a group conversation — a shared context identifier that spans all individual person sessions present simultaneously.

**Semantic search:** Finding information by meaning rather than keyword matching. Uses vector similarity between embeddings.

**Session:** In KaraOS, a Python dictionary tracking the state of one person's current interaction with the system.

**Shadow mode:** Running a new algorithm in parallel with the production algorithm, logging divergences but not affecting behavior. Used for safe validation before cutover.

**Softmax:** A function that converts a vector of raw numbers into probabilities that sum to 1.0. Used in classification models to produce class probabilities.

**SORT:** Simple Online and Realtime Tracking. An algorithm that combines Kalman filter prediction with Hungarian assignment for multi-object tracking.

**System prompt:** Instructions given to a language model before every conversation turn. Defines the model's persona, rules, context, and available tools.

**Temporal buffer:** In KaraOS (V3), a per-track buffer that accumulates multiple frames' worth of face embeddings and averages them for more stable recognition.

**Threshold:** A decision boundary. In face recognition, "is the cosine similarity above 0.28?" In voice routing, "is the voice score above 0.40?"

**Token:** The unit of text that language models process. Roughly 3-4 characters or 0.75 words in English. "The quick brown fox" is 4 tokens.

**Tool call:** When a language model generates a structured request for external computation (like searching the web or updating a database) alongside its text response.

**Transformer:** The neural network architecture underlying almost all modern language models. Key innovation: self-attention, which allows any part of the input to directly influence any other part.

**TTS (Text-to-Speech):** Converting text to spoken audio. Kokoro and Piper in KaraOS.

**VAD (Voice Activity Detection):** Detecting whether audio contains speech. Used to determine when to start and stop recording.

**Vector:** An ordered list of numbers. In AI, embeddings are vectors.

**Weights:** The learned parameters in a neural network. Stored as files; loading a model means loading its weights.

**Wilson lower bound:** A conservative estimate of the true probability of success given observed successes and failures. Used in KaraOS's graph classifier to prevent overconfidence on sparsely-observed scenarios.

**Worker thread / asyncio task:** A unit of work running concurrently with the main conversation loop. Background operations (knowledge extraction, memory compression) run as tasks or threads so they don't block the conversation.

**Yaw:** Rotation around the vertical axis — how much a face is turned left or right. The V2 quality gate rejects faces with |yaw| > 60°.

---

*This document was written based on the complete KaraOS source code, session history, test suite, and architecture documentation. Every design decision and technical choice described here is reflected in the actual code at `C:\Users\jagan\dog-ai\dog-ai\`.*
