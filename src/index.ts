import type { Core } from '@strapi/strapi'

const USER_ME_ACTION = 'plugin::users-permissions.user.me'

/**
 * Detects an existing user.me permission for the Authenticated role.
 * Strapi 5’s DB layer expects relation filters in nested form (`role: { id }`), matching
 * `findPublicPermissions` (`role: { type: 'public' }`). A plain `role: id` predicate can
 * miss rows, causing duplicate creates on every boot.
 */
async function findUserMePermissionsForRole(
  strapi: Core.Strapi,
  authRoleId: number | string,
): Promise<Array<{ id: number | string }>> {
  const permissionQuery = strapi.db.query('plugin::users-permissions.permission')

  const primary = await permissionQuery.findMany({
    where: {
      action: USER_ME_ACTION,
      role: { id: authRoleId },
    },
    limit: 25,
  })

  if (primary.length > 0) {
    return primary
  }

  const legacyShape = await permissionQuery.findMany({
    where: {
      action: USER_ME_ACTION,
      role: authRoleId,
    },
    limit: 25,
  })

  return legacyShape
}

/**
 * Ensures Authenticated users can call GET /api/users/me (required for the Nuxt app session).
 * A missing row causes Strapi's users-permissions strategy to throw Forbidden (403).
 *
 * Content-API JWT users must use the Users & Permissions role with type `authenticated`
 * (Admin panel “Super Admin” accounts use a separate admin auth system and are unrelated).
 */
async function ensureAuthenticatedUserMePermission(strapi: Core.Strapi): Promise<void> {
  const authRole = await strapi.db.query('plugin::users-permissions.role').findOne({
    where: { type: 'authenticated' },
  })

  if (!authRole) {
    strapi.log.warn(
      '[bootstrap] Users & Permissions: no role with type "authenticated"; cannot ensure user.me',
    )
    return
  }

  if (authRole.id === undefined || authRole.id === null) {
    strapi.log.warn('[bootstrap] Users & Permissions: authenticated role has no id; cannot ensure user.me')
    return
  }

  if (authRole.type !== 'authenticated') {
    strapi.log.warn(
      `[bootstrap] Users & Permissions: unexpected role type "${String(authRole.type)}" for authenticated query`,
    )
  }

  const existing = await findUserMePermissionsForRole(strapi, authRole.id)

  if (existing.length > 1) {
    strapi.log.warn(
      `[bootstrap] Duplicate permission rows (${existing.length}) for ${USER_ME_ACTION} on Authenticated role; clean up in Admin → Users & Permissions → Roles → Authenticated`,
    )
  }

  if (existing.length >= 1) {
    return
  }

  await strapi.db.query('plugin::users-permissions.permission').create({
    data: {
      action: USER_ME_ACTION,
      role: authRole.id,
    },
  })

  const roleLabel = typeof authRole.name === 'string' ? authRole.name : 'Authenticated'

  strapi.log.info(
    `[bootstrap] Added Users & Permissions action ${USER_ME_ACTION} for Authenticated role "${roleLabel}" (id=${String(authRole.id)})`,
  )
}

export default {
  register(/* { strapi }: { strapi: Core.Strapi } */) {},

  async bootstrap({ strapi }: { strapi: Core.Strapi }) {
    await ensureAuthenticatedUserMePermission(strapi)
  },
}
