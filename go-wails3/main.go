package main

import (
	"context"
	"embed"
	"log"
	"os"
	"path/filepath"
	"runtime"

	"github.com/biaggii/Proxy-Chains/go-wails3/internal/autostart"
	runtimecore "github.com/biaggii/Proxy-Chains/go-wails3/internal/runtime"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/security"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/service"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/store"
	"github.com/wailsapp/wails/v3/pkg/application"
	"github.com/wailsapp/wails/v3/pkg/events"
)

//go:embed all:frontend/dist
var assets embed.FS

//go:embed build/appicon.png
var trayIcon []byte

func main() {
	configDir, err := os.UserConfigDir()
	if err != nil {
		log.Fatalf("resolve user config directory: %v", err)
	}
	database, err := store.OpenSQLite(filepath.Join(configDir, "ChainPort Gateway", "chainport.db"))
	if err != nil {
		log.Fatalf("open application database: %v", err)
	}
	defer database.Close()

	secretStore := security.NewOSKeyringStore()
	appContext, cancelApp := context.WithCancel(context.Background())
	defer cancelApp()
	var app *application.App
	workspaceService, err := service.NewWorkspaceServiceWithPickers(appContext, database, secretStore, func() (string, error) {
		if app == nil {
			return "", nil
		}
		return app.Dialog.OpenFile().SetTitle("Import ChainPort state.json").AddFilter("ChainPort state.json", "state.json;*.json").PromptForSingleSelection()
	}, func(coreName string) (string, error) {
		if app == nil {
			return "", nil
		}
		dialog := app.Dialog.OpenFile().SetTitle("Select " + coreName + " executable")
		if runtime.GOOS == "windows" {
			dialog.AddFilter("Executable files", "*.exe;*.EXE")
		} else {
			dialog.AddFilter("Executable files", "*")
		}
		return dialog.PromptForSingleSelection()
	}, func(event runtimecore.Event) {
		if app != nil {
			app.Event.Emit("core:runtime", event)
		}
	})
	if err != nil {
		log.Fatalf("load application workspace: %v", err)
	}
	if err := autostart.SetEnabled(workspaceService.GetWorkspace().Settings.RunOnStartup); err != nil {
		log.Printf("could not synchronize system startup registration: %v", err)
	}
	workspaceService.StartSubscriptionScheduler(appContext)
	settings := workspaceService.GetWorkspace().Settings
	app = application.New(application.Options{
		Name:        "ChainPort Gateway",
		Description: "Cross-platform proxy chain manager",
		Services:    []application.Service{application.NewService(workspaceService)},
		Assets:      application.AssetOptions{Handler: application.AssetFileServerFS(assets)},
		Mac:         application.MacOptions{ApplicationShouldTerminateAfterLastWindowClosed: !(settings.CloseToTray || settings.MinimizeOnStart)},
	})

	hiddenOnLaunch := settings.MinimizeOnStart
	for _, argument := range os.Args[1:] {
		if argument == "--autostart" {
			hiddenOnLaunch = true
		}
	}
	window := app.Window.NewWithOptions(application.WebviewWindowOptions{
		Title: "ChainPort Gateway", Width: 1440, Height: 900, Hidden: hiddenOnLaunch,
		Mac:              application.MacWindow{InvisibleTitleBarHeight: 50, Backdrop: application.MacBackdropTranslucent, TitleBar: application.MacTitleBarHiddenInset},
		BackgroundColour: application.NewRGB(15, 23, 42), URL: "/",
	})

	if settings.CloseToTray || settings.MinimizeOnStart {
		tray := app.SystemTray.New()
		tray.SetIcon(trayIcon)
		tray.SetTooltip("ChainPort Gateway")
		menu := app.NewMenu()
		menu.Add("Show ChainPort").OnClick(func(_ *application.Context) { window.Show() })
		menu.Add("Start Core").OnClick(func(_ *application.Context) {
			go func() {
				if err := workspaceService.StartCore(); err != nil {
					app.Event.Emit("core:runtime", runtimecore.Event{Type: "error", Message: err.Error(), Snapshot: workspaceService.GetRuntimeStatus()})
				}
			}()
		})
		menu.Add("Stop Core").OnClick(func(_ *application.Context) { _ = workspaceService.StopCore() })
		menu.AddSeparator()
		menu.Add("Quit").OnClick(func(_ *application.Context) { app.Quit() })
		tray.SetMenu(menu).OnClick(func() { window.Show() })
		if settings.CloseToTray {
			window.RegisterHook(events.Common.WindowClosing, func(event *application.WindowEvent) { window.Hide(); event.Cancel() })
		}
	}

	app.Event.OnApplicationEvent(events.Common.ApplicationStarted, func(_ *application.ApplicationEvent) {
		if workspaceService.GetWorkspace().Settings.AutoStart {
			go func() {
				if err := workspaceService.StartCore(); err != nil {
					app.Event.Emit("core:runtime", runtimecore.Event{Type: "error", Message: err.Error(), Snapshot: workspaceService.GetRuntimeStatus()})
				}
			}()
		}
	})
	app.OnShutdown(func() { _ = workspaceService.StopCore(); cancelApp() })

	if err := app.Run(); err != nil {
		_ = workspaceService.StopCore()
		cancelApp()
		log.Fatal(err)
	}
	_ = workspaceService.StopCore()
	cancelApp()
}
