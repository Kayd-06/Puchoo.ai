export function can(user, capability) {
  return user?.capabilities?.[capability] === true;
}
