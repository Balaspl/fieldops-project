# Technician push notifications

The mobile app registers an Expo push token, and the backend sends assignment
notifications through the Expo Push Service. The backend does not use Firebase
Admin or need a Firebase service-account secret.

## Android push credentials

Android delivers remote notifications through FCM. Expo Push Service handles
that connection for the backend, but the Expo/EAS project still needs its FCM V1
service credential configured. The app already points to
`mobile/android/app/google-services.json` for the Android client configuration.
Upload the matching FCM V1 service-account key to the Android credentials for
this EAS project using `eas credentials` or the Expo dashboard. Keep that
private key in Expo/EAS credentials; do not put it in the backend `.env`, mobile
app, or source control.

An `EXPO_ACCESS_TOKEN` backend environment variable is optional. When set, it is
sent to Expo as a bearer token to authenticate push requests.

## Confirm delivery path

1. Install a development, preview, or production app build on a physical
   Android phone. Expo Go cannot register remote push tokens.
2. Allow FieldOps notifications in Android system settings.
3. After technician sign-in, check backend logs for `Registered technician push
   token.`
4. Assign a job and check backend logs for an Expo Push Service response. A
   successful ticket means Expo accepted the message for delivery; Expo push
   receipts can provide later provider errors.

The app creates the high-priority `fieldops_job_assignments_v2` channel with
vibration. Android can still suppress banners if notifications are disabled
for the app or channel.
