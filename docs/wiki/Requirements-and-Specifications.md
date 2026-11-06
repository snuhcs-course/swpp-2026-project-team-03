# ROCKY — AI-Powered Band Scores

Team 03 · 영양실조 \| Version 0.3 \| November 6, 2026

## 1. Document Revision History

| Version | Date | Major changes |
|---|---|---|
| 0.1 | 2026-10-09 | Initial requirements reflecting the confirmed band-arrangement scope, full-song 4/4 support, account-based arrangement library, and planned musician evaluations. |
| 0.2 | 2026-10-23 | Narrowed the scope from re-arranging any song for any lineup to band songs only: parts in the original are transcribed as recorded, and only selected instruments absent from the original are generated. Rewrote US-03 and NFR-02 accordingly; added US-11 (sign-up and sign-out), US-12 (form a team), US-13 (share a song with my team), labeling of AI-generated parts, and NFR-10 (per-user results, except songs shared with the owner's team); reordered US-01/US-02 so the lineup is chosen before upload, as in the app; added a survey-findings section (48 respondents) mapped to requirements; added Iteration 2 implementation status and planned improvements (multi-song upload, per-song progress, browsing while processing, background processing, key change); updated the wireframe, scope boundaries, and validation plan. Removed the 4/4-only input restriction, which came from the dropped arrangement model. |
| 0.3 | 2026-11-06 | Connected the requirements to the working app, server, and final pipeline. Added US-14 (enter the original lineup) and US-15 (track progress while using the app, from PL-02 and PL-03). Added one or two guitars to US-01 and two-guitar handling to US-03. Rewrote US-07 and US-10 for server-side accounts and results; removed US-08 (recovering a song after the app is fully closed); rewrote US-09 to cover sharing and saving PDF and MIDI files; replaced team member lookup with invite codes in US-12 and made one shared library per band the target of US-13. Fixed the input to MP3 and WAV, replaced the band-song restriction with a notice on the upload screen, set the latency target, redefined lineup fidelity for guitar counts, and revised the access-control and device requirements. Added PL-07 (cancel removes queued GPU work) and removed PL-01 (multi-song upload) and PL-05 (key change). Added live versions to the scope, and moved key change, lyric alignment, and score editing out of scope. Redrew the wireframe with transition arrows and failure handling, and updated the evaluation set, musician evaluation, and scope. Selected seven user stories for UAT and linked them to the requirements. |

## 2. Project Abstract

ROCKY is an Android application that turns a recording of a band song into rehearsal-ready scores for the instruments a band actually has. University band clubs often spend hours transcribing parts by ear, and a member whose instrument is not in the original song usually sits out. With ROCKY, a user selects a lineup of keyboard, one or two guitars, bass, and drums, uploads a full-length MP3 or WAV recording, and enters the original lineup or chooses "I don't know." ROCKY transcribes each selected instrument that appears in the original as recorded, and generates a fitting part, marked as AI-generated, for each selected instrument the original lacks. When guitar counts differ, it compresses two guitars into one playable part or generates a second guitar. Users receive an individual score for every selected instrument and a full score, with tablature for guitar and bass. They can follow processing while using the app, listen to synthesized audio while reading a score, save results to a Library, share or save PDF and MIDI files, and share selected songs with their band.

## 3. Customer

Primary customers are university band-club members who play songs written for keyboard, guitar, bass, and drums, and who need scores that match the original recording. The key use case is a band with a member whose instrument does not appear in the original song: that member needs a new part that fits the song, while the other members need their parts transcribed as recorded. Secondary customers are individual amateur instrumentalists who want an as-recorded score for their instrument.

| Customer type | Typical need |
|---|---|
| Band with an instrument the song lacks | Get as-recorded parts for the instruments in the original and a new part for the extra member (e.g., a keyboardist). |
| Band with the same lineup as the original | Get as-recorded scores for every member without transcribing by ear. |
| Band whose guitar count differs from the original | Get one playable guitar part from two original guitars, or a generated second guitar part when the original has one guitar. |
| Band missing an instrument of the song | Get as-recorded scores for the instruments the band does have. ROCKY does not re-arrange the missing part onto other instruments. |
| Individual instrumentalist | Get an as-recorded score, with TAB for guitar and bass, for their own instrument. |

### 3.1 Requirements Survey

In October 2026 the team surveyed 48 band-club members (guitar 22, drums 11, keyboard 7, bass 7, vocals 1). Instrument-specific questions were answered only by players of that instrument. The table links each finding to the requirement it supports; findings that point outside the current scope are listed too, so the scope decisions are visible.

| Finding | Respondents | Reflected in |
|---|---|---|
| Play rock or band music | 48 / 48 | Band-song focus (NFR-01, Section 9) |
| At least 60% of songs played in the past year were originally performed by band instruments | 38 / 48 | Band-song focus (NFR-01) |
| When the original lacks an instrument the team has, that member sits the song out or the team gives up the song | 37 / 48 | Generated parts for missing instruments (US-03) |
| Gave up a song because a score existed but not for our lineup (e.g., no piano score) | 16 / 48 | US-03 |
| Would use an app that gives each part of a band song exactly as recorded (4–5 / 5) | 42 / 48 | As-recorded transcription (US-03) |
| Would use an app that keeps the original parts and adds only our missing instruments (4–5 / 5) | 28 / 48 | US-03 |
| Riffs, solos, and drum fills must stay as in the original (mean, 1–5) | 3.88 | Transcribe existing parts instead of re-arranging (US-03, Section 9) |
| Expect an AI score to be "almost perfect" before using it (others: 80% correct and fix a little 14, only chords and rhythm 4) | 30 / 48 | Accuracy evaluation (NFR-05, Section 8) |
| After getting a score, still have to fix wrong parts by hand | 24 / 48 | NFR-05; score editing is out of scope (Section 9) |
| Spend more than one hour preparing one song's part | 24 / 48 | Customer need (Section 3) |
| Prepare parts from paid score sites 35, YouTube covers 32, by ear 26 (multiple choice) | — | Competitive landscape (Section 4) |
| Guitarists who prefer TAB or TAB with standard notation | 20 / 22 | TAB for guitar (US-05) |
| Bassists who prefer TAB or both | 7 / 7 | TAB for bass (US-05) |
| Keyboardists who prefer a two-hand (grand-staff) score | 6 / 7 | Musician evaluation of notation readability (Section 8) |
| Drummers who need fills in the score (exact fills 7, basic pattern with main fills 4) | 11 / 11 | NFR-05, Section 8 |
| Guitarists who say a score split into rhythm and lead parts is necessary when there are two guitars (4–5 / 5) | 16 / 22 | Two-guitar handling (US-01, US-03, US-14) |
| Would wait 10 minutes or more for a result (5 minutes or less: 5) | 31 / 48 | Latency target (NFR-04) |
| Single feature respondents would pick (Q17): live/cover version 18, as recorded 13, re-arrange non-band songs 12, as recorded plus missing parts 5 | — | Core scope stays as recorded plus missing parts (US-03); live versions are in scope, and cover versions are considered only if time remains (Section 9) |
| Original part missing from our team happens often (4–5 / 5); usually another instrument covers it (37) or the part is dropped (22) | 26 / 48 | Out of scope: re-arranging for a smaller lineup (Section 9) |
| Gave up a song because the original was not a band song | 20 / 48 | Not blocked; the upload screen warns about poor results (US-02, NFR-01) |
| Most wanted extra features: backing track without my instrument 30, key change 27, score editing 24, playback while reading the score 22, sharing with members 16, difficulty adjustment 12 | — | Sharing with members: US-12, US-13. Playback while reading the score: US-06. Key change, score editing, backing tracks, and difficulty adjustment are out of scope (Section 9) |

## 4. Competitive Landscape

ROCKY combines uploaded-audio analysis with as-recorded transcription of every band part and generation of parts the original lacks, delivered as playable notation. The table summarizes the primary product emphasis of the comparable services; ROCKY entries describe functionality in the Iteration 3 app.

| Capability | Moises | Guitar2Tabs | Songsterr | ROCKY |
|---|---|---|---|---|
| Analyze an uploaded recording | O | O | △ | O |
| Notation or TAB for recorded parts | X | O (guitar, bass) | O (library songs) | O |
| New part for an instrument the song lacks | X | X | X | O |
| Individual and full-band scores | X | X | △ (library songs) | O |
| Audio playback of the result | O | X | O | O |

O: supported. X: not supported. △: limited. Moises can separate recorded parts and work with audio, but it does not deliver a score for each band member.

Unlike transcription-only tools, ROCKY also writes new parts for instruments the original song does not use, so every member of the band has something to play. Unlike audio-stem generation tools, its principal deliverable is rehearsal-ready notation rather than audio alone.

## 5. Functional Requirements

The following user stories describe the mandatory release scope. Every story has a testable Given–When–Then acceptance scenario. Acceptance criteria check that the right parts are delivered in the right form; transcription accuracy and the musical quality of generated parts are assessed separately (Section 8). Section 5.1 reports what the Iteration 3 app implements. US-08 was removed in this version.

### US-01 Choose the Band Lineup

As a band member, I want to select any non-empty combination of keyboard, one or two guitars, bass, and drums, so that the scores match our available instruments.

> **AC-01-1:** Given I start a new request, when I choose at least one supported instrument, with one or two guitars if guitar is selected, and continue, then the request records exactly that lineup and the app moves to song upload.
>
> **AC-01-2:** Given no instrument is selected, when I attempt to continue, then the app prevents it and requests at least one instrument.

### US-02 Upload a Full-Length Song

As a band member, I want to upload an MP3 or WAV recording of a band song, so that I can get scores for a song I want to perform.

> **AC-02-1:** Given I am signed in, have chosen a lineup, and have selected a decodable MP3 or WAV recording, when I confirm the song and complete the original-lineup step, then the app uploads the recording, creates a score request for that lineup, and shows its status.
>
> **AC-02-2:** Given I select a corrupted or unsupported file, when I attempt to upload it, then the app explains the failure and permits another selection.
>
> **AC-02-3:** Given I am on the upload screen, when I choose a song, then the app shows a notice that songs not played by band instruments may give poor results.

### US-03 Get Transcribed and Generated Parts

As a band member, I want ROCKY to transcribe the parts that are in the original song and generate parts for our instruments that the original lacks, so that every member of our band can play the song without transcribing by ear.

> **AC-03-1:** Given a band song and a supported lineup have been submitted, when the job completes successfully, then every selected instrument that appears in the original is delivered as a part transcribed from the recording.
>
> **AC-03-2:** Given a selected instrument does not appear in the original, when the job completes successfully, then a newly generated part is delivered for that instrument and is labeled as AI-generated.
>
> **AC-03-3:** Given the original contains an instrument that I did not select, when the job completes successfully, then no part for that instrument is delivered and the other delivered parts are not re-arranged to cover it.
>
> **AC-03-4:** Given the server cannot complete the request, when the job fails, then the app displays the failure reason and a retry action rather than a misleading completed result.
>
> **AC-03-5:** Given the original has two guitars and my lineup has two guitars, when the job completes successfully, then the guitars are delivered as two separated parts.
>
> **AC-03-6:** Given the original has one guitar and my lineup has two guitars, when the job completes successfully, then the original guitar is delivered as a transcribed part and the second guitar is delivered as a generated part labeled as AI-generated.
>
> **AC-03-7:** Given the original has two guitars and my lineup has one guitar, when the job completes successfully, then the guitars are delivered as one part that one player can perform.

### US-04 Read Individual and Ensemble Scores

As an instrumentalist, I want to switch between my instrument score and the complete ensemble score, so that I can practice my part and understand its role in the band.

> **AC-04-1:** Given a completed result is open, when I choose an available instrument, then its individual score is displayed.
>
> **AC-04-2:** Given a completed result is open, when I select the full band, then a combined score for all chosen instruments is displayed.
>
> **AC-04-3:** Given a score is displayed, when I move through it, then I can reach every page of that score.

### US-05 View Guitar and Bass Tablature

As a guitarist or bassist, I want to view tablature for my part, so that I can rehearse in a familiar string-and-fret notation.

> **AC-05-1:** Given a completed result includes guitar or bass, when I open that part's score, then the score includes tablature for that part.
>
> **AC-05-2:** Given an instrument other than guitar or bass is selected, when I inspect its score, then the app does not offer an unsupported TAB conversion.

### US-06 Listen to the Result

As a band member, I want to play synthesized audio of the delivered parts while reading the score, so that I can hear the result before rehearsal.

> **AC-06-1:** Given a completed result has prepared audio, when I press Play, then the app plays the full band or selected instrument and offers a stop or pause control.
>
> **AC-06-2:** Given audio is not yet available, when I open its playback area, then the app communicates its status without silently failing.
>
> **AC-06-3:** Given audio is playing, when I switch between the full band and an instrument, then playback continues from the same position and the score can follow the playback position.

### US-07 Save and Reopen a Result

As a registered user, I want to access previous results in my Library, so that I do not need to rerun expensive inference for each rehearsal.

> **AC-07-1:** Given a completed result is open while I am signed in, when I save it, then it appears in my Library with its lineup and available scores.
>
> **AC-07-2:** Given a saved result exists, when I reopen it, then its previously generated outputs are displayed without automatically rerunning the pipeline.
>
> **AC-07-3:** Given I saved a result, when I sign out and sign back in with the same account, including on another device, then the same result opens from my Library.

### US-09 Export and Save Scores

As a band member, I want to send score files to other devices and save them on my phone, so that I can print or distribute rehearsal materials.

> **AC-09-1:** Given a completed result is open, when I select PDF or MIDI files and share them, then the files are sent through the Android share flow and can be opened on another device.
>
> **AC-09-2:** Given a completed result is open, when I select PDF or MIDI files and save them, then the files are stored on my phone and can be opened there.

### US-10 Sign In to My Library

As a registered user, I want to sign in to my account, so that my saved results remain associated with me.

> **AC-10-1:** Given valid account credentials are provided, when I sign in, then the app opens with my account and my account-linked Library is available.
>
> **AC-10-2:** Given authentication fails, when I try to sign in, then the app shows an error without revealing another user's results.

### US-11 Create an Account and Sign Out

As a new user, I want to create an account with a nickname and the part I play, and to sign out when I am done, so that my results are kept under my own account and my part is ready when I start a new request.

> **AC-11-1:** Given I enter a valid email and verification code, password, password confirmation, nickname, and the required agreements, when I submit the sign-up form, then my account is created and I am signed in.
>
> **AC-11-2:** Given the email or nickname is already registered, or a field is invalid, when I submit the sign-up form, then the app shows an error on that field and does not create an account.
>
> **AC-11-3:** Given I chose an instrument as my part, when I start a new request, then that instrument is preselected in the lineup selection and I can change it.
>
> **AC-11-4:** Given I am signed in, when I sign out, then the app returns to the sign-in screen and my Library is not accessible until I sign in again.

### US-12 Form a Band

As a band member, I want to create a band and let my bandmates join with an invite code, so that I can share scores with the people I rehearse with.

> **AC-12-1:** Given I am signed in, when I create a band, then the app creates a six-character invite code that I can copy and send.
>
> **AC-12-2:** Given I have a valid invite code, when I enter it, then I join that band and appear in its member list with my part.
>
> **AC-12-3:** Given the invite code is invalid, when I try to join, then the app shows an error and I do not join a band.

### US-13 Share a Song with My Band

As a band member, I want to share selected results with my band's shared library, so that every member can open the same scores on their own device without processing the song again.

> **AC-13-1:** Given a completed result is available and I belong to a band, when I share it with that band, then every member sees it in the band's shared library on their own device and can view its scores, play its audio, and export its files.
>
> **AC-13-2:** Given I have not shared a song, when a band member opens the band's shared library, then that song does not appear.
>
> **AC-13-3:** Given I do not belong to a band, when I open the share option for a song, then the app asks me to create or join a band first.

### US-14 Enter the Original Lineup

As a band member, I want to tell ROCKY which instruments the original song uses, so that it transcribes those parts and generates only what the original lacks.

> **AC-14-1:** Given I have selected a song, when I choose the original instruments, including one or two guitars, then the app shows which parts will be generated and records the original lineup.
>
> **AC-14-2:** Given I do not know the original lineup, when I choose "I don't know," then ROCKY determines the original instruments from the recording and labels generated parts from that result.
>
> **AC-14-3:** Given the original has no guitar and my lineup has two guitars, when I try to start, then the app prevents it and explains that ROCKY can generate only one guitar in this case.
>
> **AC-14-4:** Given I chose neither an original instrument nor "I don't know," when I try to start, then the app prevents it.

### US-15 Track Progress While Using the App

As a band member, I want to see each song's progress while I use other screens, so that I know when each result will be ready and can continue using the app.

> **AC-15-1:** Given a song is processing, when I open the progress tab, then the song is listed with its current stage and percentage.
>
> **AC-15-2:** Given a song is processing, when I move to another tab, then processing continues and I can use that tab.
>
> **AC-15-3:** Given a song is waiting for the GPU or for another song, when I open the progress tab, then the app shows that it is waiting.
>
> **AC-15-4:** Given a job failed after its upload finished, when I choose retry, then the app reconnects to the server job without uploading the song again.

### 5.1 Iteration 3 Implementation Status

The Iteration 3 Android app ([`iteration-3-demo`](https://github.com/snuhcs-course/swpp-2026-project-team-03/tree/iteration-3-demo)) uploads real songs to the ROCKY server, which processes them on a GPU through the final pipeline. A demo song remains available without the server. Accounts, Library entries, and bands are currently stored only on the device. Live processing currently needs the phone to be connected to a laptop over USB, and that laptop must stay connected to the server.

| Story | Status in Iteration 3 |
|---|---|
| US-01 | Implemented, including one or two guitars. |
| US-02 | Partial. Upload, status, and the band-instrument notice are implemented. The file picker accepts any audio file and the server also accepts FLAC, M4A, and OGG, so both must be restricted to MP3 and WAV. |
| US-03 | Implemented for live server jobs, including failure reason and retry. After a failure the app can also open the bundled demo result, which is a demonstration fallback and not part of the requirement. |
| US-04 | Implemented for full-band and per-instrument PDF scores. |
| US-05 | Implemented in guitar and bass PDF scores. There is no separate TAB screen. |
| US-06 | Implemented for full-band and per-instrument synthesized MP3, including position-preserving part changes and score following. |
| US-07 | Partial. Saving, renaming, deleting, and reopening work on the same device. AC-07-3 on another device needs the server-side account and Library database. |
| US-09 | Partial. PDF, MIDI, and MP3 sharing is implemented. Saving directly to phone storage (AC-09-2) is not implemented. |
| US-10 | Partial. Sign-in is implemented with a device-local account database. A server-side account database is planned. |
| US-11 | Partial. The sign-up form, validation, part preselection, and sign-out are implemented on the device. The verification code is shown on screen instead of being sent by email. |
| US-12 | Partial. Creating, joining, and leaving bands by invite code are implemented between accounts on the same device. Joining from another device needs the server-side database. |
| US-13 | Partial. Sharing works between accounts on the same device. One shared library per band across devices needs the server-side database. |
| US-14 | Implemented, including "I don't know" and the two-guitar block. |
| US-15 | Implemented while the app stays open. |

### 5.2 Planned Improvements (Not Mandatory)

The team plans the following improvements. They are not part of the mandatory release scope above and may change. PL-02 (per-song progress) and PL-03 (browsing while processing) moved to US-15 in this version. PL-01 (multi-song upload), PL-05 (key change), and PL-06 (non-band song warning after processing) were removed.

**PL-04 Process in the Background.** As a band member, I want processing to continue while the app is in the background, so that I can use other apps while I wait. *Status: the server continues processing. The app has no background service to guarantee progress updates or result download while it is in the background.*

> **AC-PL-04-1:** Given songs are processing, when I move the app to the background and later return to it, then processing has continued and the progress screen shows the current progress.

**PL-07 Cancel Server Processing.** As a band member, I want cancelling a song to stop its server work, so that the GPU becomes available for other songs. *Status: partial. Cancelling removes the song from the app, but the server job continues.*

> **AC-PL-07-1:** Given a song is queued or processing, when I cancel it, then the server removes it from the queue or stops its GPU work.

## 6. Non-functional Requirements

Requirements below are testable where possible.

| ID | Category | Requirement / verification |
|---|---|---|
| NFR-01 | Input scope | Accept decodable MP3 and WAV audio of full-length songs, including live versions. ROCKY is designed for band songs, i.e., songs whose instrumental parts are played by keyboard, guitar, bass, and/or drums. Other songs are not blocked, and the upload screen warns that they may give poor results. |
| NFR-02 | Lineup fidelity | Functional tests shall verify all 23 possible non-empty requested lineups (keyboard, bass, and drums each on or off, with zero to two guitars). Delivered parts must match the requested lineup, selected instruments present in the original must be transcribed, and selected instruments absent from the original must be generated and labeled AI-generated. The guitar cases 2→2, 2→1, 1→1, 1→2, 0→1, and blocked 0→2 shall each be verified. |
| NFR-03 | Processing robustness | While the app stays open, a lost connection does not lose an accepted job, and retry reconnects to it. If the app is fully closed during processing, the song is not recovered and must be uploaded again. |
| NFR-04 | Performance | A 3-minute song shall complete within 10 minutes, measured from the start of processing with a GPU available. Time spent waiting for a free GPU is reported separately. Record median, 90th-percentile, and failure rates for complete song processing. In the survey, 31 of 48 respondents would wait 10 minutes or more, and 5 would wait 5 minutes or less. |
| NFR-05 | Musical usability | Transcription is evaluated against reference MIDI. After TAB and keyboard processing, delivered parts shall contain no onsets one player cannot play and no notes outside the instrument range. Scores must be evaluated for physical playability, rhythmic legibility, musical fit, and rehearsal readiness using a consistent musician evaluation protocol. |
| NFR-06 | Output integrity | Generated PDF documents must open and contain parts for the intended instrument(s); audio must correspond to the saved result. |
| NFR-07 | Access control | Only the account owner and, for shared songs, members of the owner's band may retrieve a saved result. Passwords are never stored in plain text. After a job completes, the server deletes the uploaded audio and separated stems and keeps only the result files. Results of a deleted Library entry must also be removed from the server. |
| NFR-08 | Device compatibility | Core workflows shall be tested on Android 13 on the team's Galaxy phones. The app supports Android 8 (API 26) and later. |
| NFR-09 | Resource reuse | Opening a saved result does not trigger new AI inference; repeat-request caching, if provided, must distinguish source audio and lineup settings. |
| NFR-10 | Per-user results | Each user's results are stored separately. A result generated for one user is never reused or shown for another user, even when the same song and lineup are requested, unless the owner has shared that song with their band (US-13). |

**Changes from v0.2 and current gaps**

| ID | Change from v0.2 | Reason and current gap |
|---|---|---|
| NFR-01 | Kept MP3 and WAV, added live versions, and removed the plan to reject non-band songs. | The team decided to warn users instead of detecting non-band songs. The server must reject the other formats it currently accepts. |
| NFR-02 | Replaced 15 combinations with 23 lineups and six guitar cases. | Guitar can now be one or two parts, and generation depends on the original lineup. |
| NFR-03 | Removed recovery after the app is fully closed. | The team decided not to implement it. Retry remains available while the app is open. |
| NFR-04 | Replaced the pending target with a 10-minute target. | The survey and evaluation threshold T5 now give a target. T5 measures the GPU stage, while this requirement measures completion and must be measured on the current pipeline. |
| NFR-05 | Added the playability limit. | Evaluation threshold T6 and keyboard playability processing now cover it. |
| NFR-07 | Stated the retention behavior and the deletion requirement. | The server has no user accounts yet. It returns a result to anyone who has the job ID and can reach the server, so owner-only access is not met until the server-side account database is added. Deleting a Library entry does not yet remove server results. |
| NFR-08 | Replaced Galaxy S22 and S23 with Android 13 Galaxy phones and added Android 8 support. | The team's demo phones run Android 13, and the original minimum version of Android 14 could not be installed on them. |

## 7. User Interface Requirements

The Android UI must make the path from lineup selection to scores clear. Screens and transitions must specify both valid user actions and recoverable failures. The bottom tabs are New Score, Progress, Library (the Storage tab in the Design Documentation), and My Band. The wireframes below are a low-fidelity functional specification. Black arrows show transitions and the user input that causes them. Red dashed boxes show inputs that are not allowed and how the app handles failures.

**Figure 1. Creating and using a score**

![ROCKY wireframe: creating and using a score](https://raw.githubusercontent.com/snuhcs-course/swpp-2026-project-team-03/docs/reqspec-v0.3/docs/images/ROCKY-wireframe-1-score-flow-v0.3.png)

**Figure 2. Account, Library, and band**

![ROCKY wireframe: account, Library, and band](https://raw.githubusercontent.com/snuhcs-course/swpp-2026-project-team-03/docs/reqspec-v0.3/docs/images/ROCKY-wireframe-2-account-band-v0.3.png)

### 7.1 Screen Specifications

| Screen | Key actions | Validation / failure handling |
|---|---|---|
| Sign-in / sign-up / profile | Sign in; sign up with email verification; edit nickname, part, and photo; sign out. | Sign-in errors; sign-up field errors and duplicate email/nickname. |
| Lineup selection | Toggle keyboard, drums, bass, and guitar; set one or two guitars (own part preselected); continue to upload. | Block empty selection; clearly display chosen configuration. |
| Upload | Select MP3/WAV or the demo song; check the server connection. | Invalid or undecodable file; choose another file. A notice warns that songs not played by band instruments may give poor results. |
| Original lineup | Select the original instruments or "I don't know"; review parts to be generated; start processing. | Block when nothing is selected; block two guitars when the original has none. |
| Progress | View queued, waiting, running, completed, and failed songs with stage, percentage, and time left; open a result; retry; cancel or remove. | Failure reason and retry while the app stays open. |
| Score viewer | Choose full band or part; read all PDF pages with TAB where available; play audio; follow the score; save; share with a band; export. Generated parts carry an AI-generated label. | Indicate unavailable audio or files. |
| Export | Select band and part files; share them; save them to the phone. | Indicate unavailable files; failed export feedback. |
| Library | List saved results; reopen; rename; delete. | Empty Library state. |
| My Band | Create or join a band by invite code; copy the code; view members and parts; share scores; open the band's shared library; leave. | Invalid invite code; sharing without a band prompts to create or join one. |

## 8. Validation and Planned Evaluation

**AI evaluation (Iteration 3).** The team declared the evaluation set and thresholds on 2026-11-03, before the runs. `eval/eval_set.csv` on `ml/eval-set` contains 129 cases: 12 RWC band songs for separation and transcription, 103 other RWC songs for a transcription baseline, and 14 commercial band songs for whole-pipeline and playability checks. Separation and transcription use the F1 metrics in Section 3.3 of the MuScriptor paper. Beat alignment moves notes to a 16th-note grid, so it is not judged by time-based F1. Generated parts have no reference answer, so they are evaluated with automatic metrics, playability checks, and human ratings. Thresholds and results are recorded in the [Testing Documentation](Testing-Documentation).

| ID | Check | Pass if |
|---|---|---|
| T1 | Multi F1 with and without separation | The adopted separator beats no separation |
| T2 | Multi F1, BS-RoFormer against Demucs | BS-RoFormer is at least as high |
| T3 | Keyboard onset F1, BS-RoFormer against Demucs | BS-RoFormer is higher |
| T4 | Valid output on 14 band songs | 100% of songs |
| T5 | GPU stage time for a 3-minute song | 10 minutes or less |
| T6 | Unplayable onsets and out-of-range notes | 0 |

**Musician evaluation.** Twelve band musicians evaluate the pipeline's scores and MIDI on three prepared songs in a written interview, with responses due on November 8. The 21-question form covers playing experience, listening to the original and MIDI, reading the score, playability, and rehearsal use. Existing parts are judged by how well they reproduce the original, and generated parts by how well they fit the song. These sessions are formative score evaluations, not substitutes for app-based UAT.

Findings will be grouped by instrument and failure type, used to prioritize pipeline and notation changes, and then re-evaluated. Functional coverage of the lineups in NFR-02 will be verified independently of subjective performance quality.

**User acceptance test.** The team selected the seven user stories below as the key stories for UAT. They are fixed from the end of Iteration 3. Pass conditions and test procedures are defined in the Acceptance Testing section of the [Testing Documentation](Testing-Documentation). In-class UAT takes place on November 16.

| ID | User story | Requirements | Status for UAT |
|---|---|---|---|
| AT1 | Enter the band and original lineups, upload a song, and receive scores | US-01, US-02, US-03, US-14, NFR-04 | Implemented. Latency must be measured on the current pipeline. |
| AT2 | Receive a part for an instrument in our lineup that the original lacks | US-03 | Implemented. |
| AT3 | Receive parts for a band with two guitars | US-01, US-03, US-14 | Implemented. |
| AT4 | Follow progress while using other screens | US-03, US-15 | Implemented. |
| AT5 | Listen to the audio while reading the score | US-04, US-06 | Implemented. |
| AT6 | Reopen a saved score later | US-07, US-10 | Implemented on the same device. Other devices need the server-side database. |
| AT7 | Export scores | US-09 | Sharing is implemented. Saving to the phone must be implemented. |

## 9. Scope Boundaries and Pending Decisions

| Confirmed for initial release | Still to decide / refine |
|---|---|
| Full-length MP3/WAV inputs, including live versions; a notice that songs not played by band instruments may give poor results; lineups of keyboard, bass, drums, and one or two guitars; original lineup input with "I don't know"; as-recorded transcription for selected instruments in the original; generated parts, labeled AI-generated, for selected instruments the original lacks; two-guitar separation, compression, and second-guitar generation; individual and ensemble scores; TAB for guitar/bass; synthesized audio playback; progress tracking while the app stays open; sign-up, sign-in, and sign-out; Library; PDF and MIDI sharing and saving; bands with invite codes and one shared library per band; per-user results. Planned, not mandatory: background processing and server-side cancellation. | Server access from a phone without a connected laptop; handling several users with one GPU per workspace; design of the server-side account and band database; whether the owner can stop sharing a song. |
| Out of scope: re-arranging a song for a smaller lineup, except compressing two original guitars for a one-guitar band (other instruments of the original that the band lacks are not redistributed to other parts); detecting or blocking songs not played by band instruments; recovering a song after the app is fully closed during processing; uploading several songs in one request; key change; lyric alignment in the score; score editing; difficulty adjustment; source-separation backing tracks; generating two guitars when the original has no guitar. Cover versions will be considered only if time remains. | Known limitations: songs not played by band instruments can give poor results; when the original lineup is unknown, automatic guitar-count detection can be wrong (3 of 14 songs in testing), and the user's input is more reliable; if detection finds no guitar and the band requests two, the job fails; parts can still switch between instruments mid-song; some notes are classified as "other" instruments; the timing stage assumes a single tempo for the whole song; Library, account, and band data remain on one device until the server-side database is added. |

Development context (not a user-facing requirement): the app sends the requested and original lineups to a server. The server separates the recording into instrument tracks, transcribes the selected tracks, aligns notes to beats and bars, prepares playable guitar, bass, and keyboard parts, generates parts the original lacks, and publishes PDF, MIDI, and MP3 files. The earlier M2M arrangement approach was dropped because it altered the original riffs and fills. Technical details are in the [Design Documentation](Design-Documentation), and evaluation details are in the [Testing Documentation](Testing-Documentation).
