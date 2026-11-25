/*
 * Copyright (C) 2026 ChiefGyk3D
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami

MouseArea {
    id: compact

    Layout.minimumWidth: Kirigami.Units.iconSizes.small
    Layout.minimumHeight: Kirigami.Units.iconSizes.small

    hoverEnabled: true
    acceptedButtons: Qt.LeftButton
    onClicked: root.expanded = !root.expanded

    Kirigami.Icon {
        anchors.fill: parent
        // One icon, four states, no text: the tray gives every item a
        // square. "Something is parked" is the only device state worth a
        // glance -- the penguin loses its signal and the disc goes grey.
        // Network Repair on is worth more: a dark disc with cellular bars,
        // checked before parked, because it is what the owner turned on to
        // fix the network. A missing helper is worth the popup's sentence, so
        // it stays the theme's warning icon. The SVGs ship inside the
        // package: no icon theme, no install step of their own.
        source: root.helperMissing
            ? "dialog-warning"
            : Qt.resolvedUrl(root.repairActive
                ? "../icons/hammunition-devices-repair.svg"
                : (root.anyParked
                    ? "../icons/hammunition-devices-parked.svg"
                    : "../icons/hammunition-devices-awake.svg"))
        active: compact.containsMouse
    }
}
