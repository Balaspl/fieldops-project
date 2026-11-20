
import React, { useState } from 'react';
import {
  Alert,
  ImageBackground,
  ScrollView,
  Text,
  View,
} from 'react-native';
import {
  KeyRound,
  Mail,
  ShieldCheck,
  UserRound,
  LockKeyhole,
  Leaf,
} from 'lucide-react-native';

import { api } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import {
  Card,
  ErrorBanner,
  Field,
  PrimaryButton,
} from '../components/UI';

function getProfileErrorMessage(
  error: unknown,
  fallback: string
): string {
  if (typeof error === 'object' && error !== null) {
    const err = error as {
      message?: string;
      response?: {
        data?: {
          detail?: string;
          message?: string;
        };
      };
    };

    return (
      err.response?.data?.detail ||
      err.response?.data?.message ||
      err.message ||
      fallback
    );
  }

  return fallback;
}

export default function ProfileScreen() {
  const { user, reloadUser } = useAuth();

  const [firstName, setFirstName] = useState(user?.first_name || '');
  const [lastName, setLastName] = useState(user?.last_name || '');

  const [savingProfile, setSavingProfile] = useState(false);

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  const [savingPassword, setSavingPassword] = useState(false);
  const [error, setError] = useState('');

  const saveProfile = async () => {
    setError('');

    if (!firstName.trim() || !lastName.trim()) {
      setError('First name and last name are required.');
      return;
    }

    setSavingProfile(true);

    try {
      await api.put('/auth/profile', {
        first_name: firstName.trim(),
        last_name: lastName.trim(),
      });

      await reloadUser();

      Alert.alert(
        'Profile updated',
        'Your staff profile name has been updated.'
      );
    } catch (e) {
      setError(
        getProfileErrorMessage(e, 'Profile update failed.')
      );
    } finally {
      setSavingProfile(false);
    }
  };

  const changePassword = async () => {
    setError('');

    if (!currentPassword || !newPassword || !confirmPassword) {
      setError('Complete all password fields.');
      return;
    }

    if (newPassword !== confirmPassword) {
      setError('New password and confirmation do not match.');
      return;
    }

    if (newPassword.length < 8) {
      setError('Use at least 8 characters for the new password.');
      return;
    }

    setSavingPassword(true);

    try {
      await api.put('/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
      });

      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');

      Alert.alert(
        'Password changed',
        'Your password has been updated.'
      );
    } catch (e) {
      setError(
        getProfileErrorMessage(e, 'Password change failed.')
      );
    } finally {
      setSavingPassword(false);
    }
  };

  const fullName =
    `${user?.first_name || ''} ${user?.last_name || ''}`.trim();

  const roleLabel =
    user?.role === 'super_admin' ? 'SUPER ADMIN' : 'DISPATCHER';

  return (
    <ImageBackground
      source={require('../../../assets/team/nature_team_background.png')}
      resizeMode="cover"
      imageStyle={{ opacity: 1 }}
      style={{
        flex: 1,
        backgroundColor: '#E8F1E6',
      }}
    >
      <ScrollView
        style={{
          flex: 1,
          backgroundColor: 'transparent',
        }}
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{
          paddingHorizontal: 14,
          paddingTop: 14,
          paddingBottom: 34,
          gap: 13,
          backgroundColor: 'transparent',
        }}
      >
        {/* Page heading */}
        <View
          style={{
            paddingHorizontal: 3,
            paddingVertical: 5,
            gap: 4,
          }}
        >
          <Text
            style={{
              color: '#103F2B',
              fontSize: 27,
              fontWeight: '900',
              letterSpacing: -0.8,
            }}
          >
            My Profile
          </Text>

          <Text
            style={{
              color: '#244F3A',
              fontSize: 12,
              fontWeight: '600',
            }}
          >
            Manage your FieldOps identity and account security
          </Text>
        </View>

        {error ? <ErrorBanner message={error} /> : null}

        {/* Profile identity card */}
        <Card
          style={{
            padding: 15,
            borderRadius: 21,
            borderColor: '#CFE3D0',
            backgroundColor: 'rgba(255,255,255,0.95)',
            gap: 12,
            shadowColor: '#17432B',
            shadowOpacity: 0.10,
            shadowRadius: 6,
            shadowOffset: { width: 0, height: 3 },
            elevation: 3,
          }}
        >
          <View
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 12,
            }}
          >
            <View
              style={{
                width: 57,
                height: 57,
                borderRadius: 19,
                backgroundColor: '#E2F3E3',
                borderWidth: 1,
                borderColor: '#CFE3D0',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <UserRound size={28} color="#075B36" />
            </View>

            <View style={{ flex: 1, gap: 5 }}>
              <Text
                style={{
                  color: '#103F2B',
                  fontSize: 18,
                  fontWeight: '900',
                }}
              >
                {fullName || 'FieldOps Staff'}
              </Text>

              <View
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: 5,
                }}
              >
                <ShieldCheck size={13} color="#16813C" />

                <Text
                  style={{
                    color: '#16813C',
                    fontSize: 10,
                    fontWeight: '900',
                  }}
                >
                  {roleLabel}
                </Text>
              </View>
            </View>
          </View>

          <View
            style={{
              height: 1,
              backgroundColor: '#E0EADF',
            }}
          />

          <View
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 9,
            }}
          >
            <View
              style={{
                width: 34,
                height: 34,
                borderRadius: 12,
                backgroundColor: '#EAF4E9',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Mail size={16} color="#075B36" />
            </View>

            <View style={{ flex: 1, gap: 2 }}>
              <Text
                style={{
                  color: '#718477',
                  fontSize: 9,
                  fontWeight: '800',
                }}
              >
                EMAIL ADDRESS
              </Text>

              <Text
                style={{
                  color: '#244F3A',
                  fontSize: 12,
                  fontWeight: '700',
                }}
              >
                {user?.email || 'Email not available'}
              </Text>
            </View>
          </View>

          <View
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 9,
            }}
          >
            <View
              style={{
                width: 34,
                height: 34,
                borderRadius: 12,
                backgroundColor: '#EAF4E9',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <ShieldCheck size={16} color="#075B36" />
            </View>

            <View style={{ flex: 1, gap: 2 }}>
              <Text
                style={{
                  color: '#718477',
                  fontSize: 9,
                  fontWeight: '800',
                }}
              >
                ORGANIZATION
              </Text>

              <Text
                style={{
                  color: '#244F3A',
                  fontSize: 12,
                  fontWeight: '700',
                }}
              >
                {user?.organization_name || 'Organization staff'}
              </Text>
            </View>
          </View>
        </Card>

        {/* Personal information */}
        <View
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            gap: 7,
            paddingHorizontal: 2,
            paddingTop: 3,
          }}
        >
          <Leaf size={21} color="#3C8A38" fill="#7CBF48" />

          <Text
            style={{
              color: '#103F2B',
              fontSize: 19,
              fontWeight: '900',
            }}
          >
            Personal Information
          </Text>
        </View>

        <Card
          style={{
            padding: 14,
            borderRadius: 21,
            borderColor: '#D8E8D4',
            backgroundColor: 'rgba(255,255,255,0.95)',
            gap: 13,
            shadowColor: '#17432B',
            shadowOpacity: 0.10,
            shadowRadius: 6,
            shadowOffset: { width: 0, height: 3 },
            elevation: 3,
          }}
        >
          <Text
            style={{
              color: '#244F3A',
              fontSize: 11,
              fontWeight: '700',
              lineHeight: 17,
            }}
          >
            Update your staff profile information.
          </Text>

          <Field
            label="FIRST NAME"
            value={firstName}
            onChangeText={setFirstName}
            placeholder="First name"
            left={<UserRound size={16} color="#718477" />}
          />

          <Field
            label="LAST NAME"
            value={lastName}
            onChangeText={setLastName}
            placeholder="Last name"
          />

          <PrimaryButton
            title="Save profile"
            onPress={() => void saveProfile()}
            loading={savingProfile}
          />
        </Card>

        {/* Account security */}
        <View
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            gap: 7,
            paddingHorizontal: 2,
            paddingTop: 3,
          }}
        >
          <Leaf size={21} color="#3C8A38" fill="#7CBF48" />

          <Text
            style={{
              color: '#103F2B',
              fontSize: 19,
              fontWeight: '900',
            }}
          >
            Account Security
          </Text>
        </View>

        <Card
          style={{
            padding: 14,
            borderRadius: 21,
            borderColor: '#D8E8D4',
            backgroundColor: 'rgba(255,255,255,0.95)',
            gap: 13,
            shadowColor: '#17432B',
            shadowOpacity: 0.10,
            shadowRadius: 6,
            shadowOffset: { width: 0, height: 3 },
            elevation: 3,
          }}
        >
          <View
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 9,
              marginBottom: 2,
            }}
          >
            <View
              style={{
                width: 39,
                height: 39,
                borderRadius: 14,
                backgroundColor: '#E2F3E3',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <LockKeyhole size={20} color="#075B36" />
            </View>

            <View style={{ flex: 1, gap: 2 }}>
              <Text
                style={{
                  color: '#103F2B',
                  fontSize: 14,
                  fontWeight: '900',
                }}
              >
                Change Password
              </Text>

              <Text
                style={{
                  color: '#718477',
                  fontSize: 10,
                }}
              >
                Keep your account secure with a strong password
              </Text>
            </View>
          </View>

          <Field
            label="CURRENT PASSWORD"
            value={currentPassword}
            onChangeText={setCurrentPassword}
            secureTextEntry
            placeholder="Enter current password"
          />

          <Field
            label="NEW PASSWORD"
            value={newPassword}
            onChangeText={setNewPassword}
            secureTextEntry
            placeholder="At least 8 characters"
          />

          <Field
            label="CONFIRM NEW PASSWORD"
            value={confirmPassword}
            onChangeText={setConfirmPassword}
            secureTextEntry
            placeholder="Re-enter new password"
          />

          <PrimaryButton
            title="Update password"
            onPress={() => void changePassword()}
            loading={savingPassword}
          />
        </Card>

        {/* Footer */}
        <Text
          style={{
            color: '#668071',
            fontSize: 10,
            fontWeight: '600',
            textAlign: 'center',
            paddingTop: 5,
          }}
        >
          FieldOps · Staff Account Settings
        </Text>
      </ScrollView>
    </ImageBackground>
  );
}
