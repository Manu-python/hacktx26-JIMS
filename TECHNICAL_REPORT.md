# Laser Communication Technical Report

*Hardware implementation, software architecture, and evaluation*

We built a one-way optical text communication prototype using an Arduino transmitter, a laser, a photoresistor, an ESP32 receiver, and an LCD. The transmitter represents binary data through laser on and off states. The receiver converts the detected light pattern back into text and presents the recovered message on the display. This establishes the physical communication path needed to investigate more selective and efficient data delivery.

Our broader objective is to combine optical transport with a decision algorithm that chooses which information should be sent, compressed, or stored according to urgency, importance, and value. The longer-term application is communication between future space computing systems and Earth. The present result is a tabletop proof of concept; it is not a demonstration of an orbital data center or a measured improvement over Wi-Fi.

![System diagram: Transmitter (message input, Arduino binary encoder, laser module on/off states) sends light across a free-space optical path to the Receiver (photoresistor and input circuit, ESP32 bit and text decoder, LCD received message)](images/system-diagram.png)

| Subsystem | Role in the prototype |
|---|---|
| Arduino and laser | Encode text and emit its binary sequence through light intensity. |
| Photoresistor and breadboard | Detect changes in illumination and connect the receiver input circuit. |
| ESP32 and LCD | Recover the transmitted message and display the decoded text. |
| Decision software | Choose data handling based on message value and urgency; model, algorithm details, and quantitative evaluation remain to be documented. |

**Implementation status.** The optical text path is the completed hardware result. The policy, compression, and request-driven storage behavior described in later sections define the software architecture and the next validation work; no numerical performance improvement is claimed for them.

## Optical encoding and signal recovery

### Binary representation and on-off keying

Binary encoding represents a message as a sequence of zeros and ones. On-off keying, or OOK, maps those bits to two optical intensity states. Under the conventional mapping used for explanation here, a one is represented by laser illumination and a zero by the laser being off. Both endpoints must use the same mapping, character encoding, bit order, and timing. The electrical voltage associated with light may be high or low depending on the receiver circuit; electrical polarity and logical bit value are separate choices.

| Illustrative logical bit | Optical state | Receiver interpretation |
|---|---|---|
| 1 | Laser on during the bit interval | Illuminated state |
| 0 | Laser off during the bit interval | Dark state |

For example, in an eight-bit ASCII representation, the letter A is `01000001`. This is an illustration of bit representation, not a claim about the exact character format in the current firmware. Binary encoding is not compression: representing a character as bits does not, by itself, reduce the information that must be transmitted.

### Receiver measurement and timing

The photoresistor changes resistance as the light level changes. Its input circuit must translate that change into an electrical signal that the ESP32 can distinguish. A voltage divider sampled by an analog-to-digital converter is one possible implementation; a comparator can instead provide a digital signal. Espressif documents the ESP32 analog-reading interface, but the actual pin, circuit topology, threshold, and sample timing must be captured from the installed receiver firmware and schematic. [3]

The receiver must determine both the bit value and the boundaries between bits. Long runs of zeros or ones cannot be decoded by counting transitions alone. A reliable implementation therefore needs agreed timing and a way to identify message boundaries. A preamble, defined bit period, length field, and error check are recommended additions if the current firmware does not already provide them.

### Carrier frequency and useful data rate

Optical carrier frequency is different from the rate at which the laser intensity is deliberately changed to carry bits. The ESP32 and photoresistor detect the intensity pattern; they do not count individual oscillations of the optical electromagnetic field. Professional optical links can support high data rates, but this prototype is limited by its laser driver, detector response, sampling, synchronization, and noise. A higher optical frequency alone does not establish a faster data link. [1, 2]

For binary OOK without additional coding, one bit is represented per symbol interval. Reducing that interval can raise the nominal bit rate only while the receiver can still distinguish successive symbols reliably. Our bit period, sustainable rate, and error rate require measurement before a numerical performance claim can be made.

## Implementation process and firmware responsibilities

We connected the transmitter firmware, optical hardware, receiver firmware, and LCD to establish the communication path described below.

1. **Establish the transmitter.** We used an Arduino as the transmitting controller and connected it to the laser module. Its firmware prepares the message as a binary sequence and controls the laser output so that the transmitted light represents that sequence.
2. **Encode the optical message.** We used laser on and off states to carry the encoded data through free space. A single agreed representation is needed across both endpoints so that the receiver can reconstruct the same characters that were sent.
3. **Assemble the receiver.** We connected the photoresistor through an external breadboard to the ESP32. The breadboard provides the physical connections for the light-sensing input stage. The light path must reach the photoresistor for reception to occur.
4. **Decode the detected pattern.** The ESP32 firmware interprets the received light changes as binary information and reconstructs the text message. The detector supplies a physical measurement; the firmware performs the logical interpretation and decoding.
5. **Display the recovered message.** We connected an LCD to the ESP32 and used it to display the decoded text. The display provides a visible endpoint for the communication demonstration. A complete-message log should accompany the LCD when a message is longer than the visible display area.
6. **Define the data handling layer.** We separated the communication task from the higher-level question of which message should be transmitted next. The intended decision algorithm evaluates urgency, importance, and value, then selects transmission, compression, or storage. Its implementation and results need to be documented independently from successful optical decoding.

### Configuration needed for reproduction

The reproducible build record should include the Arduino and ESP32 variants, laser module and driver, receiver circuit and resistor values, voltage levels, pin assignments, LCD model and interface, character format, bit timing, synchronization method, receive threshold, and firmware versions. The measured optical distance and lighting conditions should accompany every performance test.

> **Safety:** Before extending the circuit, verify the laser module current requirements and the ESP32 input limits. A laser module must not be assumed safe to power directly from a GPIO without its specifications. Keep the beam path fixed and terminated at the receiver, and avoid eye exposure and reflective surfaces.

## Decision software and data compression

The software architecture has two distinct responsibilities. The microcontroller firmware handles the physical message exchange: the Arduino encodes and transmits, and the ESP32 receives, decodes, and displays. A separate decision layer determines how messages should be handled before they are committed to the outgoing transmission queue. Its usefulness is measured by the information delivered under a fixed link constraint, not by whether the software is labeled intelligent.

### Inputs, outputs, and priority policy

The decision layer should receive the original message, its arrival time, source, relevant context, and current queue or link status. It should return a bounded record containing a message identifier, priority, chosen action, and short reason. The original message should remain available so that a decision can be audited and an important detail is not lost during processing.

| Proposed priority | Example | Default handling |
|---|---|---|
| Urgent | Fire, injury, evacuation, unsafe oxygen | Place ahead of routine traffic; preserve exact location, measurements, and requested action. |
| High | Degraded communication, unauthorized access, reduced cooling | Send promptly after urgent traffic; retain context and operational status. |
| Routine | Normal readings, completed checks, scheduled work | Queue, batch, or store until an appropriate transmission opportunity. |

These categories form a proposed evaluation policy for the 30 example messages in the appendix. They are human-assigned reference labels, not outputs of a tested AI model. Actual urgency depends on operating context; an apparently routine battery or temperature reading can become urgent if it crosses a system-specific limit.

### How AI can support the decision

A rule-based classifier can map defined conditions to actions. An LLM can interpret message meaning and mission instructions, then propose the same bounded output format. If an LLM is used, record its model and version, prompt, execution location, latency, and validation rules. Enforce allowed actions in ordinary code, preserve explicit emergency language, and retain a deterministic fallback when a response is invalid. A named model and its accuracy have not yet been established as project results.

### Compression must preserve meaning and save space

Lossless compression allows the receiver to recover the original bytes. AI summarization produces a shorter description but can omit information, so it must be evaluated as a lossy transformation rather than described as equivalent compression. Emergency locations, numbers, units, negations, and required actions should not be removed. For short messages, compression metadata can outweigh the savings; use a compressed representation only when its complete transmitted size is smaller than the original format.

Prioritization changes delivery order. Storage delays transmission. Neither automatically reduces the total bytes if every message is eventually sent unchanged. Measure byte reduction separately from faster delivery of urgent messages, and count headers, metadata, and retries when reporting communication savings.

## Link requests, storage, and delayed transmission

The long-term concept is to retain data onboard when it cannot be delivered and release selected data when a communication opportunity or request is available. This is a store-and-forward design. It requires the application to recognize a valid request and the link to remain usable long enough to transmit a complete message.

### Distinguish a zero from a lost connection

A laser-off interval is part of ordinary OOK data. It may represent a zero inside a valid message. Darkness can also result from an idle transmitter, blocked beam, misalignment, or loss of power. Therefore, a single dark reading cannot mean that the communication session has ended or that the system should switch to storage.

For a future request-driven implementation, define an explicit command such as `SEND_REQUEST` within a framed message. Treat a recognized command or valid heartbeat as evidence of an active session. Declare a timeout only after a defined interval without valid frames. The timeout must exceed permitted zero runs and normal message gaps, or use a line code and framing scheme that establish those limits.

| Condition | Recommended application behavior |
|---|---|
| Valid zero inside a message | Continue decoding the current frame. |
| Valid request and usable link | Select the highest-priority queued message and transmit it. |
| No valid request or expired session | Keep messages in storage; continue looking for a valid session. |
| Corrupted or incomplete frame | Reject or flag the frame; retain the source data for recovery. |
| Confirmed delivery | Mark the message delivered and apply the retention policy. |

### The current hardware path is one way

The demonstrated direction is Arduino to ESP32. The LCD confirms local reception for a person watching it; it does not provide an acknowledgment to the Arduino. If the Arduino represents a satellite transmitter and the ESP32 represents Earth, a ground request cannot travel backward through this one-way arrangement. A reverse optical channel or a separate control link is required for requests, acknowledgments, and automatic retransmission.

### Queue behavior for the next revision

Assign message IDs and timestamps, persist unsent messages, and choose the next message by priority with a rule that prevents routine data from waiting forever. Record whether a message is queued, transmitting, acknowledged, expired, or failed. A timeout should preserve the original data instead of silently deleting it. Repeated deliveries should be detected by message ID. Storage capacity, expiry rules, and recovery after power loss need explicit tests.

Decision software should operate before the constrained downlink. Sending all raw data to a remote AI service through that same constrained link before deciding what to send would consume the capacity the selection step is meant to save. Any external inference traffic must be included in the system accounting or identified as a separate preflight step.

## Current results and evaluation method

The achieved hardware result is end-to-end optical text delivery: an Arduino generates a laser-encoded binary message, the photoresistor and ESP32 recover it, and the LCD shows the decoded text. This demonstrates integration of encoding, optical modulation, sensing, decoding, and display. It establishes a working communication concept, but does not establish a numerical error rate, transfer speed, maximum distance, or improvement over Wi-Fi.

| Result or metric | Current status |
|---|---|
| Optical text transmission and LCD output | Qualitative end-to-end operation demonstrated. |
| Bit rate and useful payload throughput | Not yet quantified. |
| Distance and ambient-light tolerance | Not yet characterized by a recorded test matrix. |
| Bit errors and exact-message success rate | Require repeated trials and transmit/receive logs. |
| Priority classification and urgent-message delay | Require reference labels and decision/queue logs. |
| Compression savings and inference overhead | Require encoded-size, fidelity, timing, and resource measurements. |

### Example message set

The evaluation corpus contains 30 example text messages spanning normal readings, maintenance, communication problems, and emergencies. Their original text contains 1,206 ASCII or UTF-8 payload bytes, excluding line separators and all protocol overhead. Individual messages range from 21 to 55 bytes. These are properties of the supplied text, not measurements taken from physical sensors or the optical link. The appendix proposes 9 urgent, 6 high-priority, and 15 routine reference labels.

### Recommended controlled test

Send every corpus message without selection first, and save the intended and reconstructed text with timestamps. Then repeat the same arrival sequence using priority scheduling, and finally add the chosen compression or AI policy. Keep the bit timing, distance, illumination, framing, queue limit, and offered input rate fixed. Make the workload large enough to create contention; if the link is always idle, priority scheduling has little opportunity to help.

A practical initial protocol is ten trials for each of the thirty messages, yielding 300 planned transmissions per configuration. This is a proposed test design, not a completed experiment.

Compare complete decoded buffers rather than only the characters visible on the LCD. Include blocked-beam and long-zero-pattern tests to distinguish decoding behavior from link-loss handling.

- **Exact-message success:** correct complete messages divided by attempted messages.
- **Payload goodput:** correctly received payload bits divided by elapsed transfer time.
- **Urgent-message latency:** measured from its arrival at the decision queue to verified reception, including queueing, inference, compression, transmission, and retries.
- **Bit-error rate:** requires aligned bit-level logs; it cannot be inferred from a single successful display.

## Future improvements and technical references

### Improve the optical hardware

Characterize the actual photoresistor response before shortening the bit interval. A faster photodiode receiver with an appropriate amplifier is a future upgrade for higher modulation rates. Mechanical mounts, receiver shielding, and suitable optical filtering can improve alignment stability and rejection of ambient light. Quantify the benefit through repeated range, lighting, and error-rate tests rather than assuming a component replacement guarantees faster reliable communication.

### Strengthen the communication protocol

Add or document a preamble, payload length, sequence number, and error-detection field. Separate display updates from timing-sensitive reception so LCD operations do not interrupt sampling. A reverse acknowledgment path would enable retry limits and verified delivery. Later work can evaluate clock recovery, error-correcting codes, and alternative modulation after establishing a reliable OOK baseline.

### Validate the decision algorithm

Compare a fixed rule-based policy with the AI-assisted policy on the same messages. Test paraphrases, negation, duplicate alerts, conflicting priorities, and unfamiliar messages. Measure missed urgent messages and false urgent classifications separately. Evaluate inference latency and memory use, and keep a documented fallback. Choose compression based on total encoded size and recoverability, with stronger preservation requirements for emergency content.

### Move toward a space computing model

Extend persistent storage and request handling to emulate intermittent ground contact, then evaluate which data can be delivered during a limited contact window. Retain the distinction between this bench demonstration and a flight system: space operation would require dedicated work on pointing, link budgets, environmental qualification, power, thermal control, and reliable onboard computing. Space-based AI data centers remain the long-term motivation rather than a demonstrated capability of this prototype.

## References

1. NASA. *Optical Communications.* Explains optical transport, modulation, high data-rate motivation, pointing, and atmospheric limitations. Accessed 25 October 2026. <https://www.nasa.gov/technology/space-comms/optical-communications-overview/>
2. Dolinar, Hamkins, Moision, and Vilnrotter. *Optical Modulation and Coding*, Chapter 4, JPL DESCANSO monograph series. Background on optical intensity modulation, detection, and coding. <https://descanso.jpl.nasa.gov/monograph/series7/Descanso%207_chap04_new.pdf>
3. Espressif Systems. *Arduino ESP32 ADC API.* Background for an analog-sampling receiver; exact applicability depends on the installed circuit and firmware. Accessed 25 October 2026. <https://docs.espressif.com/projects/arduino-esp32/en/latest/api/adc.html>

## Appendix: Example messages and proposed reference labels

The priority column is a proposed human reference for evaluating the decision algorithm. It is not an observed model output or evidence that these messages have already passed through the optical link. The messages are test text, not reports of real emergencies. Messages 16 through 30 preserve the original wording, and the same proposed labeling policy applies. Classification must consider meaning and context; the presence of a number or a single keyword is not enough to determine urgency reliably.

| ID | Original message | Proposed priority |
|---|---|---|
| 1 | Temperature sensor reports 24.5 C. | Routine |
| 2 | Fire detected in Sector B. Immediate response required. | Urgent |
| 3 | Battery level at 87%. | Routine |
| 4 | System diagnostics completed successfully. | Routine |
| 5 | Emergency shutdown requested for Reactor 2. | Urgent |
| 6 | Atmospheric pressure measured at 101.3 kPa. | Routine |
| 7 | Communication link operating normally. | Routine |
| 8 | Oxygen levels dropping below safe limits. | Urgent |
| 9 | Solar panel efficiency decreased by 3%. | High |
| 10 | Worker injured in Sector A. Medical assistance needed. | Urgent |
| 11 | Routine maintenance scheduled for tomorrow. | Routine |
| 12 | Main power supply failure detected. | Urgent |
| 13 | Humidity sensor reports 45%. | Routine |
| 14 | Backup communication system activated. | High |
| 15 | Critical coolant leak detected in the main generator. | Urgent |
| 16 | Data backup completed successfully. | Routine |
| 17 | Unauthorized access detected in Control Room 3. | High |
| 18 | Sensor calibration completed. | Routine |
| 19 | External temperature increased by 2 C. | Routine |
| 20 | Emergency evacuation ordered for all personnel. | Urgent |
| 21 | Network latency increased to 250 ms. | High |
| 22 | Storage capacity is 72% full. | Routine |
| 23 | Radiation levels exceeding safety thresholds. | Urgent |
| 24 | Software update available for monitoring system. | Routine |
| 25 | Backup generator fuel level at 65%. | Routine |
| 26 | Water contamination detected in drinking supply. | Urgent |
| 27 | Routine status report requested. | Routine |
| 28 | Cooling fan 2 operating at reduced efficiency. | High |
| 29 | Primary communication link disconnected. | High |
| 30 | All monitoring systems functioning normally. | Routine |

**Urgent** indicates an explicit immediate hazard or emergency response. **High** indicates degraded operation or a security/communication event that should be handled promptly. **Routine** indicates a normal reading, completed task, or scheduled activity without an explicit immediate hazard. Actual mission context can change these labels.

**Proposed label totals:** 9 urgent, 6 high, and 15 routine messages. For example, a rise of 2 C or a battery level of 87% is not automatically an emergency without an operating limit. A primary-link disconnection describes a communication fault, but transmitting its report may itself require storage or a separate functioning link.

When evaluating compression or summaries, preserve the source message, its classification, and its transmitted representation together. Compare not only length, but whether numbers, locations, equipment identifiers, and required actions survive correctly.
