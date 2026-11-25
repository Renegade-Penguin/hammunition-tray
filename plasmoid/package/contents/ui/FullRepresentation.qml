/*
 * Copyright (C) 2026 ChiefGyk3D
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.extras as PlasmaExtras
import org.kde.kirigami as Kirigami
import "timelogic.js" as TimeLogic
import "controlslogic.js" as Controls

PlasmaExtras.Representation {
    id: full

    Layout.minimumWidth: Kirigami.Units.gridUnit * 20
    // Taller since the Controls panel: four groups and the Time section
    // under one another. What does not fit scrolls.
    Layout.minimumHeight: Kirigami.Units.gridUnit * 28

    header: PlasmaExtras.PlasmoidHeading {
        RowLayout {
            anchors.fill: parent
            PlasmaExtras.Heading {
                Layout.fillWidth: true
                level: 4
                text: root.controlStrings.heading
            }
            PlasmaComponents.BusyIndicator {
                running: root.acting
                visible: running
                implicitWidth: Kirigami.Units.iconSizes.small
                implicitHeight: Kirigami.Units.iconSizes.small
            }
        }
    }

    PlasmaComponents.ScrollView {
        id: scroll
        anchors.fill: parent
        contentWidth: availableWidth

        ColumnLayout {
            id: panel
            width: scroll.availableWidth
            spacing: Kirigami.Units.smallSpacing

            // The Controls panel's first group: today's rows, unchanged.
            PlasmaExtras.Heading {
                Layout.fillWidth: true
                level: 5
                text: root.controlStrings.group_devices
            }

            // The helper is absent. Say what to run; a dead switch would be
            // worse than a sentence, because a switch implies it could work.
            PlasmaExtras.PlaceholderMessage {
                Layout.fillWidth: true
                Layout.preferredHeight: Kirigami.Units.gridUnit * 8
                visible: root.helperMissing
                iconName: "dialog-warning"
                text: i18n("Device control is not installed")
                explanation: i18n("Run `hammunition hardware apply` to install the helper and the polkit action that authorises it.")
            }

            PlasmaExtras.PlaceholderMessage {
                Layout.fillWidth: true
                Layout.preferredHeight: Kirigami.Units.gridUnit * 8
                visible: !root.helperMissing && root.devices !== null && root.devices.length === 0
                iconName: Qt.resolvedUrl("../icons/hammunition-devices-awake.svg")
                text: i18n("No parkable device is attached")
                explanation: i18n("A device is parkable when its catalog entry carries a power_control block and it is plugged in now.")
            }

            ListView {
                Layout.fillWidth: true
                // The scroll view scrolls the panel; the list is as tall as its rows.
                Layout.preferredHeight: contentHeight
                interactive: false
                visible: !root.helperMissing && root.devices !== null && root.devices.length > 0
                clip: true
                model: root.devices || []

                delegate: RowLayout {
                    width: ListView.view ? ListView.view.width : 0
                    spacing: Kirigami.Units.smallSpacing

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        PlasmaComponents.Label {
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                            text: modelData.summary || modelData.name
                        }
                        PlasmaComponents.Label {
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                            opacity: 0.7
                            font: Kirigami.Theme.smallFont
                            // The bus address is what distinguishes two of a kind,
                            // and it is what the operator would type. A kept
                            // device says so whether or not it is still plugged
                            // in, and an absent one says that too.
                            text: modelData.attached === false
                                ? i18n("%1 at %2, kept off, not attached", modelData.name, modelData.address)
                                : (modelData.kept
                                    ? i18n("%1 at %2, kept off", modelData.name, modelData.address)
                                    : i18n("%1 at %2", modelData.name, modelData.address))
                        }
                    }

                    PlasmaComponents.Switch {
                        // Bound to the state the helper reported, and rebound
                        // immediately on toggle. A dismissed polkit prompt
                        // therefore leaves the switch showing the truth rather
                        // than the intent -- nothing was written, so nothing moves.
                        //
                        // Hidden for a device that is no longer attached: there is
                        // nothing to park or wake, only to forget.
                        visible: modelData.attached !== false
                        checked: !modelData.parked
                        enabled: !root.acting
                        onToggled: {
                            const wantAwake = checked;
                            checked = Qt.binding(() => !modelData.parked);
                            root.act(modelData, !wantAwake);
                        }
                    }

                    PlasmaComponents.Button {
                        // The only action left for a kept device that has been
                        // unplugged: "wake" on an absent device clears its kept
                        // flag, which is what drops it off this list.
                        visible: modelData.attached === false
                        enabled: !root.acting
                        text: i18n("Forget")
                        onClicked: root.forget(modelData)
                    }
                }
            }

            PlasmaComponents.Label {
                Layout.fillWidth: true
                visible: root.lastError !== ""
                wrapMode: Text.WordWrap
                color: Kirigami.Theme.negativeTextColor
                text: root.lastError
            }

            PlasmaComponents.Label {
                Layout.fillWidth: true
                visible: root.actionError !== ""
                wrapMode: Text.WordWrap
                color: Kirigami.Theme.negativeTextColor
                text: root.actionError
            }

            PlasmaComponents.Label {
                Layout.fillWidth: true
                visible: !root.helperMissing
                wrapMode: Text.WordWrap
                opacity: 0.7
                font: Kirigami.Theme.smallFont
                // Stated because it used to be the single most surprising
                // property of the feature; the engine can now keep a device
                // off across reboots (Hammunition D-056), so the sentence no
                // longer claims a reboot always wakes everything.
                text: i18n("Off stays off across reboots until you turn it back on.")
            }

            // The Services group (helper contract v1): per service a running
            // switch and a "start at login" checkbox. The rows are the helper's
            // with the operator's pending request applied, so a toggle shows at
            // once and the next poll confirms it. A user-scope service runs the
            // helper directly; a system-scope one asks for the password, like
            // park and wake. controlslogic.js has every rule and sentence.
            Kirigami.Separator {
                Layout.fillWidth: true
                visible: !root.helperMissing
            }

            PlasmaExtras.Heading {
                Layout.fillWidth: true
                visible: !root.helperMissing
                level: 5
                text: root.controlStrings.group_services
            }

            PlasmaComponents.Label {
                Layout.fillWidth: true
                visible: !root.helperMissing && root.servicesUnsupported
                wrapMode: Text.WordWrap
                opacity: 0.7
                text: root.controlStrings.update
            }

            PlasmaComponents.Label {
                Layout.fillWidth: true
                visible: !root.helperMissing && !root.servicesUnsupported && root.effectiveServices === null && root.servicesError === ""
                opacity: 0.7
                text: root.controlStrings.reading_services
            }

            PlasmaComponents.Label {
                Layout.fillWidth: true
                visible: !root.helperMissing && !root.servicesUnsupported && root.effectiveServices !== null && root.effectiveServices.length === 0
                opacity: 0.7
                text: root.controlStrings.no_services
            }

            Repeater {
                model: root.helperMissing || root.servicesUnsupported ? [] : (root.effectiveServices || [])
                delegate: RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        PlasmaComponents.Label {
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                            text: Controls.serviceLabel(modelData)
                        }
                        PlasmaComponents.Label {
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                            opacity: 0.7
                            font: Kirigami.Theme.smallFont
                            text: Controls.serviceDetail(modelData, root.tr)
                        }
                    }

                    PlasmaComponents.CheckBox {
                        text: root.controlStrings.login_label
                        enabled: Controls.loginEnabled(modelData, root.acting)
                        // Bound to the row as drawn and rebound on toggle, so a
                        // dismissed prompt leaves the truth checked.
                        checked: Controls.loginChecked(modelData)
                        onToggled: {
                            const row = modelData;
                            checked = Qt.binding(() => Controls.loginChecked(modelData));
                            root.setService(row, Controls.loginVerb(row));
                        }
                    }

                    PlasmaComponents.Switch {
                        enabled: Controls.runEnabled(modelData, root.acting)
                        checked: Controls.runChecked(modelData)
                        onToggled: {
                            const row = modelData;
                            checked = Qt.binding(() => Controls.runChecked(modelData));
                            root.setService(row, Controls.runVerb(row));
                        }
                    }
                }
            }

            PlasmaComponents.Label {
                Layout.fillWidth: true
                visible: !root.helperMissing && root.servicesError !== ""
                wrapMode: Text.WordWrap
                color: Kirigami.Theme.negativeTextColor
                text: root.servicesError
            }

            // The Radios group: one switch each. A radio whose tool is absent
            // names it and is disabled. Direct, never pkexec.
            Kirigami.Separator {
                Layout.fillWidth: true
                visible: !root.helperMissing
            }

            PlasmaExtras.Heading {
                Layout.fillWidth: true
                visible: !root.helperMissing
                level: 5
                text: root.controlStrings.group_radios
            }

            PlasmaComponents.Label {
                Layout.fillWidth: true
                visible: !root.helperMissing && root.radiosUnsupported
                wrapMode: Text.WordWrap
                opacity: 0.7
                text: root.controlStrings.update
            }

            PlasmaComponents.Label {
                Layout.fillWidth: true
                visible: !root.helperMissing && !root.radiosUnsupported && root.effectiveRadios === null && root.radiosError === ""
                opacity: 0.7
                text: root.controlStrings.reading_radios
            }

            PlasmaComponents.Label {
                Layout.fillWidth: true
                visible: !root.helperMissing && !root.radiosUnsupported && root.effectiveRadios !== null && root.effectiveRadios.length === 0
                opacity: 0.7
                text: root.controlStrings.no_radios
            }

            Repeater {
                model: root.helperMissing || root.radiosUnsupported ? [] : (root.effectiveRadios || [])
                delegate: RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        PlasmaComponents.Label {
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                            text: Controls.radioLabel(modelData, root.tr)
                        }
                        PlasmaComponents.Label {
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                            opacity: 0.7
                            font: Kirigami.Theme.smallFont
                            visible: text !== ""
                            text: Controls.radioDetail(modelData, root.tr)
                        }
                    }

                    PlasmaComponents.Switch {
                        enabled: Controls.radioEnabled(modelData, root.acting)
                        checked: modelData.enabled
                        onToggled: {
                            const row = modelData;
                            const wantOn = checked;
                            checked = Qt.binding(() => modelData.enabled);
                            root.setRadio(row, wantOn);
                        }
                    }
                }
            }

            PlasmaComponents.Label {
                Layout.fillWidth: true
                visible: !root.helperMissing && root.radiosError !== ""
                wrapMode: Text.WordWrap
                color: Kirigami.Theme.negativeTextColor
                text: root.radiosError
            }

            // The Uplink group: which link owns the default routes. Auto is
            // Ethernet, then Wi-Fi, then cellular; Cell first puts cellular on
            // top for an emergency or a diagnosis, until it expires. Cell first
            // uses mobile data, so it asks first (an inline question, not a
            // dialog: a dialog can close the popup under it). Always direct,
            // never pkexec or sudo. controlslogic.js has every rule and sentence.
            Kirigami.Separator {
                Layout.fillWidth: true
                visible: !root.helperMissing
            }

            PlasmaExtras.Heading {
                Layout.fillWidth: true
                visible: !root.helperMissing
                level: 5
                text: root.controlStrings.group_uplink
            }

            PlasmaComponents.Label {
                Layout.fillWidth: true
                visible: !root.helperMissing && root.uplinkUnsupported
                wrapMode: Text.WordWrap
                opacity: 0.7
                text: root.controlStrings.update
            }

            PlasmaComponents.Label {
                Layout.fillWidth: true
                visible: !root.helperMissing && !root.uplinkUnsupported && root.effectiveUplink === null && root.uplinkError === ""
                opacity: 0.7
                text: root.controlStrings.reading_uplink
            }

            // Where the routes are, and when Cell first ends; or why the
            // control is not available, plainly, with nothing to press.
            PlasmaComponents.Label {
                Layout.fillWidth: true
                visible: !root.helperMissing && !root.uplinkUnsupported && root.effectiveUplink !== null
                wrapMode: Text.WordWrap
                text: root.effectiveUplink === null ? "" : Controls.uplinkIndicator(root.effectiveUplink, Date.now() / 1000, root.tr)
            }

            Repeater {
                model: (root.helperMissing || root.uplinkUnsupported || root.effectiveUplink === null || !root.effectiveUplink.present) ? [] : Controls.UPLINK_MODES
                delegate: PlasmaComponents.RadioButton {
                    Layout.fillWidth: true
                    text: Controls.uplinkModeLabel(modelData, root.tr)
                    enabled: root.effectiveUplink !== null && Controls.uplinkEnabled(root.effectiveUplink, root.acting)
                    // Bound to the row as drawn and rebound on toggle, so a
                    // declined question leaves the truth checked.
                    checked: root.effectiveUplink !== null && Controls.uplinkChecked(root.effectiveUplink, modelData)
                    onToggled: {
                        const wanted = modelData;
                        checked = Qt.binding(() => root.effectiveUplink !== null && Controls.uplinkChecked(root.effectiveUplink, modelData));
                        root.setUplink(wanted);
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                visible: !root.helperMissing && !root.uplinkUnsupported && root.effectiveUplink !== null && root.effectiveUplink.present
                spacing: Kirigami.Units.smallSpacing

                PlasmaComponents.Label {
                    Layout.fillWidth: true
                    text: root.controlStrings.uplink_duration_heading
                }

                PlasmaComponents.ComboBox {
                    id: durationChoice
                    enabled: root.effectiveUplink !== null && Controls.uplinkDurationEnabled(root.effectiveUplink, root.acting)
                    model: Controls.UPLINK_DURATIONS.map(d => Controls.uplinkDurationLabel(d[0], root.tr))
                    currentIndex: Controls.UPLINK_DURATIONS.findIndex(d => d[0] === root.uplinkDuration)
                    onActivated: index => {
                        root.setUplinkDuration(Controls.UPLINK_DURATIONS[index][0]);
                        currentIndex = Qt.binding(() => Controls.UPLINK_DURATIONS.findIndex(d => d[0] === root.uplinkDuration));
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                visible: !root.helperMissing && root.uplinkConfirming !== ""
                spacing: Kirigami.Units.smallSpacing

                PlasmaComponents.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    text: Controls.uplinkConfirmText(root.uplinkDuration, root.tr)
                }

                RowLayout {
                    spacing: Kirigami.Units.smallSpacing

                    PlasmaComponents.Button {
                        text: root.controlStrings.uplink_confirm_yes
                        enabled: !root.acting
                        onClicked: root.confirmUplink()
                    }

                    PlasmaComponents.Button {
                        text: root.controlStrings.uplink_confirm_no
                        onClicked: root.cancelUplink()
                    }
                }
            }

            PlasmaComponents.Label {
                Layout.fillWidth: true
                visible: !root.helperMissing && root.uplinkError !== ""
                wrapMode: Text.WordWrap
                color: Kirigami.Theme.negativeTextColor
                text: root.uplinkError
            }

            // The Time section (Hammunition D-058): what the clock follows, and
            // the engine's four time modes. Every sentence comes from
            // timelogic.js, shared word for word with the Qt tray.
            Kirigami.Separator {
                Layout.fillWidth: true
                visible: !root.helperMissing
            }

            PlasmaExtras.Heading {
                Layout.fillWidth: true
                visible: !root.helperMissing
                level: 5
                text: i18n("Time")
            }

            PlasmaComponents.Label {
                Layout.fillWidth: true
                visible: !root.helperMissing
                wrapMode: Text.WordWrap
                // Greyed when the GPS cannot feed the clock: no ntpsec, or the
                // receiver is parked while the mode would use it. The note
                // below says which.
                opacity: root.timeGreyed ? 0.6 : 1.0
                text: TimeLogic.headline(root.timeState, root.timeUnsupported, root.tr)
            }

            Repeater {
                model: root.helperMissing ? [] : TimeLogic.notes(root.timeState, root.tr)
                delegate: PlasmaComponents.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    opacity: 0.7
                    font: Kirigami.Theme.smallFont
                    text: modelData
                }
            }

            Repeater {
                model: root.timeModes
                delegate: PlasmaComponents.RadioButton {
                    Layout.fillWidth: true
                    visible: !root.helperMissing && !root.timeUnsupported && root.timeState !== null
                    // Disabled only where `time mode` would refuse: ntpsec is
                    // not the daemon. A parked receiver greys the sentence but
                    // the mode can still be changed, to ntp-only say.
                    enabled: !root.acting && root.timeChoosable
                    opacity: root.timeGreyed ? 0.6 : 1.0
                    text: TimeLogic.modeLabel(modelData, root.tr)
                    // Bound to the mode the helper reported and rebound on
                    // toggle, so a dismissed prompt leaves the truth checked.
                    checked: root.timeState !== null && root.timeState.mode === modelData
                    onToggled: {
                        const wanted = modelData;
                        checked = Qt.binding(() => root.timeState !== null && root.timeState.mode === modelData);
                        root.setTimeMode(wanted);
                    }
                }
            }

            PlasmaComponents.Label {
                Layout.fillWidth: true
                visible: !root.helperMissing && root.timeError !== ""
                wrapMode: Text.WordWrap
                color: Kirigami.Theme.negativeTextColor
                text: root.timeError
            }
        }
    }
}
