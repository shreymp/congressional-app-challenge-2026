import { StatusBar } from 'expo-status-bar';
import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

const colors = {
  ink: '#10243B', muted: '#64748B', canvas: '#F4F8F8', panel: '#FFFFFF',
  line: '#DFE9E8', teal: '#0E8475', tealDark: '#075B55', mint: '#DDF5EC',
  mintText: '#16705A', amber: '#EF9A1B', amberSoft: '#FFF3D8',
  danger: '#D94B4B', dangerSoft: '#FFE8E8', blue: '#387DD5', blueSoft: '#E7F0FF',
};

const signals = [
  { icon: '☎', title: 'Known scam number', detail: '47 community reports', tone: 'danger', weight: '+42' },
  { icon: '✦', title: 'Urgent money request', detail: 'Language signal detected', tone: 'amber', weight: '+25' },
  { icon: '◌', title: 'Voice verification', detail: 'Not enough audio yet', tone: 'blue', weight: 'Pending' },
];

const history = [
  { caller: 'Unknown caller', time: 'Today, 2:14 PM', result: 'Blocked', tone: 'danger' },
  { caller: 'Maya Chen', time: 'Yesterday, 6:40 PM', result: 'Safe', tone: 'safe' },
  { caller: '+1 (312) 555-0189', time: 'Mon, 11:08 AM', result: 'Reviewed', tone: 'amber' },
];

function Badge({ children, tone = 'safe' }) {
  return <View style={[styles.badge, styles[`badge_${tone}`]]}><Text style={[styles.badgeText, styles[`badgeText_${tone}`]]}>{children}</Text></View>;
}

function IconButton({ icon, label, onPress, active = false }) {
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress} style={({ pressed }) => [styles.iconButton, active && styles.iconButtonActive, pressed && styles.pressed]}>
      <Text style={[styles.iconButtonIcon, active && styles.iconButtonIconActive]}>{icon}</Text>
      <Text style={[styles.iconButtonLabel, active && styles.iconButtonLabelActive]}>{label}</Text>
    </Pressable>
  );
}

function Waveform({ active }) {
  const [tick, setTick] = useState(0);
  const values = useMemo(() => [16, 27, 46, 31, 66, 41, 79, 53, 88, 42, 63, 29, 54, 73, 39, 57, 24, 46, 31, 63], []);
  useEffect(() => {
    if (!active) return undefined;
    const id = setInterval(() => setTick((value) => value + 1), 440);
    return () => clearInterval(id);
  }, [active]);
  return (
    <View style={styles.wave} accessibilityLabel={active ? 'Live audio activity visualizer' : 'Audio analysis paused'}>
      {values.map((height, index) => {
        const modifier = active ? ((tick + index * 3) % 5) * 3 : 0;
        return <View key={index} style={[styles.waveBar, { height: Math.max(10, height - modifier) }]} />;
      })}
    </View>
  );
}

function ProtectScreen({ callActive, onToggleCall, onReport }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scrollContent}>
      <View style={styles.topRow}>
        <View><Text style={styles.eyebrow}>LIVE PROTECTION</Text><Text style={styles.pageTitle}>{callActive ? 'We’re watching with you.' : 'You’re protected.'}</Text></View>
        <View style={styles.shield}><Text style={styles.shieldIcon}>✓</Text></View>
      </View>

      <View style={[styles.callCard, callActive && styles.callCardDanger]}>
        <View style={styles.callCardTop}>
          <View style={styles.callerAvatar}><Text style={styles.callerAvatarText}>?</Text></View>
          <View style={styles.callInfo}><Text style={styles.callerName}>{callActive ? 'Unknown caller' : 'No active call'}</Text><Text style={styles.callerNumber}>{callActive ? '+1 (312) 555-0189' : 'Start a protected call demo anytime'}</Text></View>
          {callActive && <View style={styles.livePill}><View style={styles.liveDot} /><Text style={styles.liveText}>02:17</Text></View>}
        </View>
        <Waveform active={callActive} />
        <View style={styles.callFooter}>
          <View style={styles.privateNote}><Text style={styles.privateLock}>⌁</Text><Text style={styles.privateText}>Audio stays on your device</Text></View>
          <Pressable accessibilityRole="button" onPress={onToggleCall} style={({ pressed }) => [styles.smallCallButton, pressed && styles.pressed]}><Text style={styles.smallCallButtonText}>{callActive ? 'End call' : 'Start demo'}</Text></Pressable>
        </View>
      </View>

      {callActive ? (
        <>
          <View style={styles.riskHeader}><View><Text style={styles.sectionKicker}>CALL RISK</Text><Text style={styles.sectionTitle}>High risk detected</Text></View><Badge tone="danger">81 / 100</Badge></View>
          <View style={styles.riskCard}>
            <View style={styles.riskGauge}><View style={styles.gaugeInner}><Text style={styles.gaugeNumber}>81</Text><Text style={styles.gaugeCaption}>HIGH</Text></View></View>
            <View style={styles.riskMessage}><Text style={styles.riskMessageTitle}>Pause before sharing anything.</Text><Text style={styles.riskMessageBody}>This caller matches several scam signals. Never share a code, password, or payment information.</Text></View>
          </View>
          <View style={styles.signalHeading}><Text style={styles.sectionTitle}>Why we’re concerned</Text><Pressable onPress={() => setExpanded(!expanded)}><Text style={styles.linkText}>{expanded ? 'Show less' : 'Details'}</Text></Pressable></View>
          {signals.slice(0, expanded ? signals.length : 2).map((signal) => (
            <View key={signal.title} style={styles.signalCard}>
              <View style={[styles.signalIcon, styles[`signal_${signal.tone}`]]}><Text style={styles.signalIconText}>{signal.icon}</Text></View>
              <View style={styles.signalCopy}><Text style={styles.signalTitle}>{signal.title}</Text><Text style={styles.signalDetail}>{signal.detail}</Text></View>
              <Text style={[styles.signalWeight, styles[`signalWeight_${signal.tone}`]]}>{signal.weight}</Text>
            </View>
          ))}
          <View style={styles.actionRow}>
            <Pressable accessibilityRole="button" onPress={onToggleCall} style={({ pressed }) => [styles.primaryAction, pressed && styles.pressed]}><Text style={styles.primaryActionText}>End call</Text></Pressable>
            <Pressable accessibilityRole="button" onPress={onReport} style={({ pressed }) => [styles.secondaryAction, pressed && styles.pressed]}><Text style={styles.secondaryActionText}>Report caller</Text></Pressable>
          </View>
          <Text style={styles.guardianNote}>● Your guardian is being notified of this high-risk call.</Text>
        </>
      ) : (
        <View style={styles.emptyCard}>
          <Text style={styles.emptyIcon}>✦</Text><Text style={styles.emptyTitle}>Protection is standing by</Text>
          <Text style={styles.emptyBody}>During a supported call, Scam Guardian checks number reputation and on-device risk signals in real time.</Text>
          <Pressable accessibilityRole="button" onPress={onToggleCall} style={({ pressed }) => [styles.primaryAction, styles.emptyButton, pressed && styles.pressed]}><Text style={styles.primaryActionText}>Run a simulated call</Text></Pressable>
        </View>
      )}
    </ScrollView>
  );
}

function ActivityScreen() {
  return <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
    <Text style={styles.eyebrow}>RECENT ACTIVITY</Text><Text style={styles.pageTitle}>Protected calls</Text>
    <View style={styles.summaryRow}><View style={styles.summaryCard}><Text style={styles.summaryValue}>12</Text><Text style={styles.summaryLabel}>Calls protected</Text></View><View style={styles.summaryCard}><Text style={[styles.summaryValue, { color: colors.danger }]}>2</Text><Text style={styles.summaryLabel}>Warnings sent</Text></View></View>
    <Text style={styles.sectionTitle}>This week</Text>
    {history.map((item) => <View key={item.time} style={styles.historyCard}><View style={[styles.historyIcon, styles[`history_${item.tone}`]]}><Text>{item.tone === 'safe' ? '✓' : item.tone === 'danger' ? '!' : '⌕'}</Text></View><View style={styles.historyCopy}><Text style={styles.historyCaller}>{item.caller}</Text><Text style={styles.historyTime}>{item.time}</Text></View><Badge tone={item.tone}>{item.result}</Badge></View>)}
    <View style={styles.infoCard}><Text style={styles.infoCardTitle}>Your privacy, by design</Text><Text style={styles.infoCardBody}>Call audio is analyzed on-device for protection. Scam Guardian only shares the minimum metadata needed for alerts and number reports.</Text></View>
  </ScrollView>;
}

function FamilyScreen() {
  return <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
    <Text style={styles.eyebrow}>YOUR CIRCLE</Text><Text style={styles.pageTitle}>Family protection</Text>
    <View style={styles.familyHero}><Text style={styles.familyHeroIcon}>♧</Text><Text style={styles.familyHeroTitle}>The Park family is protected</Text><Text style={styles.familyHeroBody}>Everyone receives a heads-up when a high-risk call needs another set of eyes.</Text></View>
    <Text style={[styles.sectionTitle, styles.membersHeading]}>Members</Text>
    {[['MP', 'Maya Park', 'Guardian · Alerts on'], ['JP', 'Jordan Park', 'Protected member · Alerts on'], ['LP', 'Lena Park', 'Protected member · Alerts on']].map(([initials, name, status], index) => <View key={name} style={styles.memberCard}><View style={[styles.memberAvatar, index === 0 && styles.memberAvatarAlt]}><Text style={styles.memberInitials}>{initials}</Text></View><View style={styles.memberCopy}><Text style={styles.memberName}>{name}</Text><Text style={styles.memberStatus}>● {status}</Text></View><Text style={styles.memberChevron}>›</Text></View>)}
    <Pressable accessibilityRole="button" onPress={() => Alert.alert('Invite ready', 'A secure family invitation link would be shared here in the connected product.')} style={({ pressed }) => [styles.addMember, pressed && styles.pressed]}><Text style={styles.addMemberText}>＋ Invite family member</Text></Pressable>
  </ScrollView>;
}

function SettingsScreen() {
  const [alerts, setAlerts] = useState(true);
  const [privacy, setPrivacy] = useState(true);
  return <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
    <Text style={styles.eyebrow}>SETTINGS</Text><Text style={styles.pageTitle}>Protection controls</Text>
    <Text style={styles.settingsGroupLabel}>CALL PROTECTION</Text>
    <View style={styles.settingsPanel}><Setting label="Live risk analysis" description="Analyze supported calls on your device" enabled /><Setting label="Guardian alerts" description="Alert your family for high-risk calls" enabled={alerts} onPress={() => setAlerts(!alerts)} /><Setting label="Private by default" description="Keep call audio and transcripts off our servers" enabled={privacy} onPress={() => setPrivacy(!privacy)} /></View>
    <Text style={styles.settingsGroupLabel}>ABOUT</Text>
    <View style={styles.settingsPanel}><Setting label="How Scam Guardian works" description="Learn about risk signals and their limits" /><Setting label="Help & report a problem" description="Get support or send feedback" /></View>
    <Text style={styles.version}>Scam Guardian prototype · v0.1</Text>
  </ScrollView>;
}

function Setting({ label, description, enabled, onPress }) {
  return <Pressable disabled={!onPress} onPress={onPress} style={({ pressed }) => [styles.setting, pressed && onPress && styles.pressed]}><View style={styles.settingCopy}><Text style={styles.settingLabel}>{label}</Text><Text style={styles.settingDescription}>{description}</Text></View>{typeof enabled === 'boolean' ? <View style={[styles.toggle, enabled && styles.toggleOn]}><View style={[styles.toggleKnob, enabled && styles.toggleKnobOn]} /></View> : <Text style={styles.memberChevron}>›</Text>}</Pressable>;
}

export default function App() {
  const [tab, setTab] = useState('Protect');
  const [callActive, setCallActive] = useState(true);
  const onReport = () => Alert.alert('Report submitted', 'Thanks for helping protect the community. This simulated report has been added to the demo reputation network.');
  const renderScreen = () => {
    if (tab === 'Activity') return <ActivityScreen />;
    if (tab === 'Family') return <FamilyScreen />;
    if (tab === 'Settings') return <SettingsScreen />;
    return <ProtectScreen callActive={callActive} onToggleCall={() => setCallActive(!callActive)} onReport={onReport} />;
  };
  return <SafeAreaView style={styles.safe}><StatusBar style="dark" />{renderScreen()}<View style={styles.tabBar}>{[['⌂', 'Protect'], ['◷', 'Activity'], ['♧', 'Family'], ['⚙', 'Settings']].map(([icon, label]) => <IconButton key={label} icon={icon} label={label} active={tab === label} onPress={() => setTab(label)} />)}</View></SafeAreaView>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.canvas }, scrollContent: { paddingHorizontal: 20, paddingTop: 20, paddingBottom: 106 },
  topRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 18 }, eyebrow: { color: colors.teal, fontSize: 11, letterSpacing: 1.4, fontWeight: '800', marginBottom: 5 }, pageTitle: { color: colors.ink, fontSize: 28, lineHeight: 34, fontWeight: '800', letterSpacing: -0.6 },
  shield: { height: 42, width: 42, borderRadius: 21, backgroundColor: colors.mint, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#B8E8D8' }, shieldIcon: { color: colors.tealDark, fontSize: 24, fontWeight: '900' },
  callCard: { backgroundColor: colors.panel, borderRadius: 22, padding: 17, borderWidth: 1, borderColor: colors.line, shadowColor: '#2C5460', shadowOpacity: 0.07, shadowRadius: 16, elevation: 2 }, callCardDanger: { borderColor: '#F2CACA' }, callCardTop: { flexDirection: 'row', alignItems: 'center' },
  callerAvatar: { width: 48, height: 48, borderRadius: 24, backgroundColor: colors.dangerSoft, alignItems: 'center', justifyContent: 'center' }, callerAvatarText: { fontSize: 25, color: colors.danger, fontWeight: '800' }, callInfo: { flex: 1, marginLeft: 12 }, callerName: { fontWeight: '800', fontSize: 17, color: colors.ink }, callerNumber: { marginTop: 2, color: colors.muted, fontSize: 13 },
  livePill: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#FDF1F1', paddingHorizontal: 9, paddingVertical: 6, borderRadius: 99 }, liveDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.danger, marginRight: 5 }, liveText: { color: colors.danger, fontSize: 12, fontWeight: '800' },
  wave: { height: 96, marginVertical: 14, backgroundColor: '#F7FAFA', borderRadius: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-evenly', paddingHorizontal: 12, overflow: 'hidden' }, waveBar: { width: 4, borderRadius: 5, backgroundColor: colors.teal }, callFooter: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }, privateNote: { flexDirection: 'row', alignItems: 'center' }, privateLock: { color: colors.teal, marginRight: 5, fontSize: 16 }, privateText: { color: colors.mintText, fontSize: 12, fontWeight: '700' }, smallCallButton: { backgroundColor: colors.ink, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10 }, smallCallButtonText: { color: '#FFF', fontSize: 12, fontWeight: '800' },
  riskHeader: { marginTop: 24, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }, sectionKicker: { color: colors.muted, fontSize: 10, letterSpacing: 1.2, fontWeight: '800', marginBottom: 3 }, sectionTitle: { color: colors.ink, fontWeight: '800', fontSize: 18 },
  badge: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 99 }, badgeText: { fontSize: 11, fontWeight: '800' }, badge_safe: { backgroundColor: colors.mint }, badgeText_safe: { color: colors.mintText }, badge_danger: { backgroundColor: colors.dangerSoft }, badgeText_danger: { color: '#B73232' }, badge_amber: { backgroundColor: colors.amberSoft }, badgeText_amber: { color: '#B46900' },
  riskCard: { backgroundColor: colors.dangerSoft, borderRadius: 20, padding: 15, marginTop: 12, flexDirection: 'row', borderWidth: 1, borderColor: '#F4CCCC', alignItems: 'center' }, riskGauge: { width: 92, height: 92, borderRadius: 46, backgroundColor: colors.danger, alignItems: 'center', justifyContent: 'center', marginRight: 14 }, gaugeInner: { width: 74, height: 74, borderRadius: 37, backgroundColor: '#FFF7F7', alignItems: 'center', justifyContent: 'center' }, gaugeNumber: { color: colors.danger, fontSize: 29, fontWeight: '900', lineHeight: 32 }, gaugeCaption: { color: '#B73232', fontSize: 9, fontWeight: '900', letterSpacing: 1 }, riskMessage: { flex: 1 }, riskMessageTitle: { color: '#8E2424', fontSize: 15, fontWeight: '800', lineHeight: 20 }, riskMessageBody: { color: '#9D4A4A', fontSize: 12, lineHeight: 17, marginTop: 4 },
  signalHeading: { marginTop: 25, marginBottom: 10, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }, linkText: { color: colors.teal, fontSize: 13, fontWeight: '800' }, signalCard: { minHeight: 72, backgroundColor: colors.panel, borderRadius: 15, padding: 12, marginBottom: 9, borderWidth: 1, borderColor: colors.line, flexDirection: 'row', alignItems: 'center' }, signalIcon: { height: 40, width: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center' }, signal_danger: { backgroundColor: colors.dangerSoft }, signal_amber: { backgroundColor: colors.amberSoft }, signal_blue: { backgroundColor: colors.blueSoft }, signalIconText: { fontSize: 19, fontWeight: '800', color: colors.ink }, signalCopy: { flex: 1, marginLeft: 11 }, signalTitle: { color: colors.ink, fontSize: 14, fontWeight: '800' }, signalDetail: { color: colors.muted, fontSize: 12, marginTop: 2 }, signalWeight: { fontSize: 12, fontWeight: '900' }, signalWeight_danger: { color: colors.danger }, signalWeight_amber: { color: '#BA7200' }, signalWeight_blue: { color: colors.blue },
  actionRow: { flexDirection: 'row', marginTop: 16, gap: 10 }, primaryAction: { flex: 1, backgroundColor: colors.tealDark, minHeight: 51, alignItems: 'center', justifyContent: 'center', borderRadius: 14 }, primaryActionText: { color: '#FFF', fontSize: 15, fontWeight: '800' }, secondaryAction: { flex: 1, backgroundColor: '#FFF', borderWidth: 1, borderColor: '#D4A7A7', minHeight: 51, alignItems: 'center', justifyContent: 'center', borderRadius: 14 }, secondaryActionText: { color: '#B53232', fontSize: 15, fontWeight: '800' }, guardianNote: { color: colors.mintText, textAlign: 'center', fontSize: 12, fontWeight: '700', marginTop: 13 },
  emptyCard: { alignItems: 'center', backgroundColor: '#FFF', borderWidth: 1, borderColor: colors.line, borderRadius: 20, marginTop: 24, padding: 28 }, emptyIcon: { fontSize: 32, color: colors.teal }, emptyTitle: { fontSize: 18, fontWeight: '800', color: colors.ink, marginTop: 10 }, emptyBody: { color: colors.muted, textAlign: 'center', lineHeight: 19, marginTop: 7, fontSize: 13 }, emptyButton: { width: '100%', marginTop: 20 },
  tabBar: { position: 'absolute', bottom: 0, left: 0, right: 0, height: 79, backgroundColor: '#FFF', borderTopWidth: 1, borderColor: colors.line, flexDirection: 'row', paddingHorizontal: 11, paddingTop: 7, justifyContent: 'space-between' }, iconButton: { flex: 1, alignItems: 'center', justifyContent: 'center', borderRadius: 13, paddingVertical: 6 }, iconButtonActive: { backgroundColor: colors.mint }, iconButtonIcon: { color: colors.muted, fontSize: 21, lineHeight: 24 }, iconButtonIconActive: { color: colors.tealDark }, iconButtonLabel: { color: colors.muted, fontSize: 10, fontWeight: '700', marginTop: 1 }, iconButtonLabelActive: { color: colors.tealDark }, pressed: { opacity: 0.72, transform: [{ scale: 0.98 }] },
  summaryRow: { flexDirection: 'row', gap: 10, marginTop: 20, marginBottom: 25 }, summaryCard: { flex: 1, backgroundColor: '#FFF', borderWidth: 1, borderColor: colors.line, borderRadius: 17, padding: 16 }, summaryValue: { fontSize: 27, fontWeight: '900', color: colors.tealDark }, summaryLabel: { color: colors.muted, fontSize: 12, marginTop: 4, fontWeight: '600' }, historyCard: { backgroundColor: '#FFF', borderRadius: 15, padding: 13, marginTop: 9, borderWidth: 1, borderColor: colors.line, alignItems: 'center', flexDirection: 'row' }, historyIcon: { height: 38, width: 38, borderRadius: 12, alignItems: 'center', justifyContent: 'center' }, history_safe: { backgroundColor: colors.mint }, history_danger: { backgroundColor: colors.dangerSoft }, history_amber: { backgroundColor: colors.amberSoft }, historyCopy: { flex: 1, marginLeft: 11 }, historyCaller: { fontSize: 14, color: colors.ink, fontWeight: '800' }, historyTime: { fontSize: 12, color: colors.muted, marginTop: 2 }, infoCard: { marginTop: 22, padding: 17, borderRadius: 18, backgroundColor: '#EAF6F5', borderWidth: 1, borderColor: '#C8E8E3' }, infoCardTitle: { fontSize: 15, fontWeight: '800', color: colors.tealDark }, infoCardBody: { fontSize: 12, lineHeight: 18, marginTop: 5, color: '#39706B' },
  familyHero: { marginTop: 18, padding: 22, borderRadius: 21, backgroundColor: colors.tealDark, alignItems: 'center' }, familyHeroIcon: { color: '#99E5D5', fontSize: 31 }, familyHeroTitle: { color: '#FFF', fontWeight: '800', fontSize: 18, marginTop: 8 }, familyHeroBody: { color: '#C9EFEB', fontSize: 12, lineHeight: 18, textAlign: 'center', marginTop: 5 }, membersHeading: { marginTop: 24 }, memberCard: { backgroundColor: '#FFF', padding: 13, borderRadius: 15, borderWidth: 1, borderColor: colors.line, flexDirection: 'row', alignItems: 'center', marginTop: 9 }, memberAvatar: { width: 43, height: 43, borderRadius: 14, backgroundColor: colors.blueSoft, alignItems: 'center', justifyContent: 'center' }, memberAvatarAlt: { backgroundColor: colors.mint }, memberInitials: { fontSize: 13, fontWeight: '900', color: colors.tealDark }, memberCopy: { flex: 1, marginLeft: 11 }, memberName: { color: colors.ink, fontWeight: '800', fontSize: 14 }, memberStatus: { color: colors.mintText, fontSize: 11, marginTop: 3 }, memberChevron: { color: '#94A3B8', fontSize: 25 }, addMember: { marginTop: 15, minHeight: 50, borderRadius: 14, borderWidth: 1, borderColor: '#9CD4C9', alignItems: 'center', justifyContent: 'center' }, addMemberText: { color: colors.tealDark, fontSize: 14, fontWeight: '800' },
  settingsGroupLabel: { color: colors.muted, fontSize: 11, fontWeight: '900', letterSpacing: 1, marginTop: 24, marginBottom: 8 }, settingsPanel: { backgroundColor: '#FFF', borderRadius: 17, borderWidth: 1, borderColor: colors.line, overflow: 'hidden' }, setting: { padding: 15, minHeight: 73, flexDirection: 'row', alignItems: 'center', borderBottomWidth: 1, borderBottomColor: '#EEF2F2' }, settingCopy: { flex: 1 }, settingLabel: { color: colors.ink, fontSize: 14, fontWeight: '800' }, settingDescription: { color: colors.muted, fontSize: 12, lineHeight: 16, marginTop: 3 }, toggle: { height: 26, width: 46, borderRadius: 14, backgroundColor: '#D4DEE0', padding: 3, justifyContent: 'center' }, toggleOn: { backgroundColor: colors.teal }, toggleKnob: { height: 20, width: 20, backgroundColor: '#FFF', borderRadius: 10 }, toggleKnobOn: { alignSelf: 'flex-end' }, version: { color: '#94A3B8', fontSize: 11, textAlign: 'center', marginTop: 26 },
});
