// Rendert Noten mit dem macOS-eigenen GS-Klangsatz offline in eine WAV-Datei.
// Aufruf: swift rendern.swift <noten.json> <ausgabe.wav>
// noten.json: {"dauer": s, "spuren": [{"programm": n, "schlagzeug": bool, "gain": g,
//              "noten": [[start, ende, tonhoehe, anschlag], ...], "pedal": [[start, ende], ...]}]}
import AVFoundation
import Foundation

struct Spur: Decodable {
    let programm: UInt8
    let schlagzeug: Bool
    let gain: Float
    let noten: [[Double]]
    let pedal: [[Double]]?
}
struct Stueck: Decodable { let dauer: Double; let spuren: [Spur] }

struct Ereignis { let zeit: Double; let art: Int; let wert: UInt8; let anschlag: UInt8 }

let args = CommandLine.arguments
guard args.count == 3 else { fatalError("noten.json und ausgabe.wav angeben") }
let stueck = try JSONDecoder().decode(Stueck.self, from: Data(contentsOf: URL(fileURLWithPath: args[1])))
let bank = URL(fileURLWithPath: "/System/Library/Components/CoreAudio.component/Contents/Resources/gs_instruments.dls")

let rate = 44100.0
let format = AVAudioFormat(standardFormatWithSampleRate: rate, channels: 2)!
let engine = AVAudioEngine()
var sampler: [(AVAudioUnitSampler, [Ereignis])] = []

for spur in stueck.spuren {
    let s = AVAudioUnitSampler()
    engine.attach(s)
    engine.connect(s, to: engine.mainMixerNode, format: format)
    s.volume = spur.gain
    let msb = spur.schlagzeug ? UInt8(kAUSampler_DefaultPercussionBankMSB) : UInt8(kAUSampler_DefaultMelodicBankMSB)
    try s.loadSoundBankInstrument(at: bank, program: spur.programm, bankMSB: msb, bankLSB: 0)
    var e: [Ereignis] = []
    for n in spur.noten {
        e.append(Ereignis(zeit: n[0], art: 1, wert: UInt8(n[2]), anschlag: UInt8(n[3])))
        e.append(Ereignis(zeit: n[1], art: 0, wert: UInt8(n[2]), anschlag: 0))
    }
    for p in spur.pedal ?? [] {
        e.append(Ereignis(zeit: p[0], art: 2, wert: 127, anschlag: 0))
        e.append(Ereignis(zeit: p[1], art: 2, wert: 0, anschlag: 0))
    }
    e.sort { ($0.zeit, $0.art) < ($1.zeit, $1.art) }
    sampler.append((s, e))
}

let block: AVAudioFrameCount = 128
try engine.enableManualRenderingMode(.offline, format: format, maximumFrameCount: block)
try engine.start()

// In einer Funktion, damit die Datei beim Verlassen geschlossen wird (sonst fehlt die Länge im Kopf).
func schreibeDatei() throws {
    let datei = try AVAudioFile(forWriting: URL(fileURLWithPath: args[2]), settings: format.settings)
    let puffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: block)!
    let gesamt = Int((stueck.dauer + 2.0) * rate)
    var frames = 0
    var zeiger = [Int](repeating: 0, count: sampler.count)

    while frames < gesamt {
        let jetzt = Double(frames) / rate
        for i in sampler.indices {
            let (s, e) = sampler[i]
            while zeiger[i] < e.count && e[zeiger[i]].zeit <= jetzt {
                let x = e[zeiger[i]]
                switch x.art {
                case 1: s.startNote(x.wert, withVelocity: x.anschlag, onChannel: 0)
                case 0: s.stopNote(x.wert, onChannel: 0)
                default: s.sendController(64, withValue: x.wert, onChannel: 0)
                }
                zeiger[i] += 1
            }
        }
        let status = try engine.renderOffline(block, to: puffer)
        guard status == .success else { fatalError("Rendern fehlgeschlagen: \(status)") }
        try datei.write(from: puffer)
        frames += Int(block)
    }
}
try schreibeDatei()
engine.stop()
