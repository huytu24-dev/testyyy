import '@mantine/core/styles.css'
import '@mantine/notifications/styles.css'
import '@mantine/dropzone/styles.css'
import '@xyflow/react/dist/style.css'
import './app.css'

import { AppShell, Badge, Burger, Group, MantineProvider, NavLink, Text, ThemeIcon, Tooltip, createTheme } from '@mantine/core'
import { ModalsProvider } from '@mantine/modals'
import { useDisclosure } from '@mantine/hooks'
import { Notifications } from '@mantine/notifications'
import { IconFlask2, IconFolders, IconKey, IconSparkles } from '@tabler/icons-react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Link, Route, Routes, useLocation } from 'react-router-dom'

import CasePage from './pages/CasePage'
import FlowPage from './pages/FlowPage'
import FlowRunPage from './pages/FlowRunPage'
import ProjectPage from './pages/ProjectPage'
import ProjectsPage from './pages/ProjectsPage'
import RunPage from './pages/RunPage'
import { useHealth, useProjects } from './queries'

const theme = createTheme({
  primaryColor: 'violet',
  defaultRadius: 'md',
  fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, sans-serif',
  fontFamilyMonospace: 'JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, monospace',
  headings: { fontWeight: '700' },
  colors: {
    dark: ['#C9CBD3', '#A6A9B6', '#7D8091', '#5C5F70', '#3A3D4C', '#2A2C38', '#1E2029', '#16171F', '#111218', '#0B0C10'],
  },
})

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 5_000, refetchOnWindowFocus: false, retry: 1 } },
})

function Health() {
  const { data, isError } = useHealth()
  if (isError) return <Badge color="red" variant="light">backend offline</Badge>
  if (!data) return null
  return (
    <Group gap={8}>
      <Tooltip label={data.llm_ready ? `${data.provider} key loaded` : `Add ${data.missing_keys.join(', ')} to .env and restart the backend`}>
        <Badge color={data.llm_ready ? 'teal' : 'red'} variant="light" leftSection={<IconKey size={12} />}>
          {data.llm_ready ? `${data.provider} ready` : `${data.missing_keys.join(', ')} missing`}
        </Badge>
      </Tooltip>
      <Badge color="gray" variant="outline">{data.model.split(':').pop()}</Badge>
    </Group>
  )
}

function Nav() {
  const { data: projects } = useProjects()
  const { pathname } = useLocation()
  return (
    <>
      <NavLink component={Link} to="/" label="All projects" leftSection={<IconFolders size={16} />} active={pathname === '/'} />
      <Text size="xs" c="dimmed" tt="uppercase" fw={700} mt="md" mb={4} px="sm">Projects</Text>
      {projects?.map((p) => (
        <NavLink
          key={p.id}
          component={Link}
          to={`/projects/${p.id}`}
          label={p.name}
          description={`${p.case_count} cases · ${p.passed_count} passed`}
          leftSection={<IconFlask2 size={16} />}
          active={pathname.startsWith(`/projects/${p.id}`)}
        />
      ))}
    </>
  )
}

function App() {
  const [navOpen, { toggle, close }] = useDisclosure(false)
  const { pathname } = useLocation()
  useEffect(close, [pathname])  // hide the mobile menu after navigating
  return (
    <AppShell header={{ height: 56 }} navbar={{ width: 250, breakpoint: 'sm', collapsed: { mobile: !navOpen } }} padding="lg">
      <AppShell.Header className="app-header">
        <Group h="100%" px="lg" justify="space-between">
          <Group gap="sm">
          <Burger opened={navOpen} onClick={toggle} hiddenFrom="sm" size="sm" />
          <Link to="/" className="brand">
            <Group gap={10}>
              <ThemeIcon size={30} radius="md" variant="gradient" gradient={{ from: 'violet', to: 'cyan', deg: 135 }}>
                <IconSparkles size={18} />
              </ThemeIcon>
              <Text fw={800} size="lg" className="brand-text">QA Agent Studio</Text>
            </Group>
          </Link>
          </Group>
          <Group visibleFrom="sm"><Health /></Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="sm">
        <Nav />
      </AppShell.Navbar>
      <AppShell.Main>
        <Routes>
          <Route path="/" element={<ProjectsPage />} />
          <Route path="/projects/:id" element={<ProjectPage />} />
          <Route path="/cases/:id" element={<CasePage />} />
          <Route path="/runs/:id" element={<RunPage />} />
          <Route path="/flows/:id" element={<FlowPage />} />
          <Route path="/flow-runs/:id" element={<FlowRunPage />} />
        </Routes>
      </AppShell.Main>
    </AppShell>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="dark">
      <Notifications position="top-right" />
      <ModalsProvider>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      </ModalsProvider>
    </MantineProvider>
  </StrictMode>,
)
